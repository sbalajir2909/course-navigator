"""
graph/graph.py
LangGraph teaching loop with MemorySaver checkpointing.

Flow:
  teach → END (pause, await student explanation via POST /api/teach/explain)
  validate → route → advance | reteach | recommend_prereqs | flag_review
  reteach → END (pause again)
  advance → END
  flag_review → END
"""
from __future__ import annotations
import json
from typing import Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import TeachingState
from agents.teaching_agent import teach_concept, select_adaptive_strategy
from agents.validator_agent import validate_explanation

STRATEGY_MAP = {1: "direct", 2: "analogy", 3: "example", 4: "decompose", 5: "simpler"}
MAX_ATTEMPTS = 5


# ─── Nodes ────────────────────────────────────────────────────────────────────

async def teaching_node(state: TeachingState) -> dict[str, Any]:
    """Generate a teaching explanation using the current (adaptive) strategy."""
    attempt = state.get("attempt_number", 1)
    strategy = state.get("teaching_strategy", "direct")
    pain_point = state.get("pain_point", "")
    strategies_used = state.get("strategies_used", [])
    explicit_confusion = state.get("explicit_confusion", False)
    pain_points = state.get("pain_points", [])

    explanation = await teach_concept(
        module=state.get("module", {}),
        student_history=state.get("student_history", []),
        source_chunks=state.get("source_chunks", []),
        strategy=strategy,
        pain_point=pain_point,
        attempt_number=attempt,
        memory_context="",
        concept_index=state.get("concept_index", 0),
        strategies_used=strategies_used,
        explicit_confusion=explicit_confusion,
        pain_points=pain_points,
    )
    # Track which strategy was actually used
    used = list(strategies_used)
    if strategy not in used:
        used.append(strategy)
    return {"current_explanation": explanation, "strategies_used": used, "explicit_confusion": False}


async def validator_node(state: TeachingState) -> dict[str, Any]:
    """Validate student's explain-back against source material."""
    student_response = state.get("student_response", "")
    attempt = state.get("attempt_number", 1)
    prior_mastery = state.get("mastery_probability", 0.3)

    result = await validate_explanation(
        student_explanation=student_response,
        module=state.get("module", {}),
        source_chunks=state.get("source_chunks", []),
        prior_mastery=prior_mastery,
        attempt_number=attempt,
        agent_explanation=state.get("agent_explanation", state.get("current_explanation", "")),
    )

    # Accumulate pain points
    pain_points = list(state.get("pain_points", []))
    if result.get("pain_point") and result["verdict"] != "MASTERED":
        pain_points.append(result["pain_point"])

    # Accumulate history
    history = list(state.get("student_history", []))
    history.append({
        "attempt_number": attempt,
        "student_explanation": student_response,
        "verdict": result["verdict"],
        "pain_point": result.get("pain_point", ""),
        "mastery_probability": result["mastery_probability"],
        "scores": result.get("scores", {}),
    })

    return {
        "last_verdict": result["verdict"],
        "pain_point": result.get("pain_point", ""),
        "pain_points": pain_points,
        "concepts_missed": result.get("concepts_missed", []),
        "feedback_to_student": result.get("feedback_to_student", ""),
        "mastery_probability": result["mastery_probability"],
        "scores": result.get("scores", {}),
        "student_history": history,
        "should_advance": result["verdict"] == "MASTERED",
        "should_flag": attempt >= MAX_ATTEMPTS,
    }


async def prereq_recommendation_node(state: TeachingState) -> dict[str, Any]:
    """Identify prerequisite topics when student fails 3+ times."""
    from api.cf_client import complete_json as cf_json

    module = state.get("module", {})
    concepts_missed = state.get("concepts_missed", [])

    prompt = f"""The student is struggling with: {module.get('title', 'this module')}
Learning objective: {', '.join(module.get('learning_objectives', [])[:2])}
They are specifically missing: {concepts_missed}

Identify 2-3 foundational prerequisite topics that would directly help them understand this.
These should be short, learnable topics — not entire courses.

Return JSON:
{{
  "prerequisite_recommendations": [
    {{
      "topic": "Name of prerequisite topic",
      "reason": "One sentence: exactly why this is blocking their understanding",
      "brief_explanation": "2-3 sentences explaining this topic simply"
    }}
  ]
}}"""

    prereqs = []
    try:
        data = await cf_json(
            messages=[{"role": "user", "content": prompt}],
            model_key="course",
            temperature=0.3,
            max_tokens=400,
        )
        prereqs = data.get("prerequisite_recommendations", [])
    except Exception:
        pass

    return {"prerequisite_modules": prereqs}


async def reteach_node(state: TeachingState) -> dict[str, Any]:
    """Set up for the next teaching attempt with adaptive strategy selection."""
    attempt = state.get("attempt_number", 1)
    new_attempt = attempt + 1
    strategies_used = state.get("strategies_used", [])
    explicit_confusion = state.get("explicit_confusion", False)
    pain_points = state.get("pain_points", [])

    new_strategy = select_adaptive_strategy(
        attempt_number=new_attempt,
        strategies_used=strategies_used,
        explicit_confusion=explicit_confusion,
        pain_points=pain_points,
    )

    return {
        "attempt_number": new_attempt,
        "teaching_strategy": new_strategy,
        "student_response": None,
    }


async def advance_node(state: TeachingState) -> dict[str, Any]:
    """Student mastered the module. Update mastery score."""
    current_mastery = state.get("mastery_probability", 0.3)
    new_mastery = min(1.0, current_mastery + 0.25)
    return {
        "mastery_probability": new_mastery,
        "should_advance": True,
    }


async def flag_review_node(state: TeachingState) -> dict[str, Any]:
    """Flag module for professor review after max attempts."""
    return {
        "should_flag": True,
        "should_advance": False,
    }


# ─── Routing ──────────────────────────────────────────────────────────────────

def route_after_validation(state: TeachingState) -> str:
    verdict = state.get("last_verdict", "NOT_YET")
    attempt = state.get("attempt_number", 1)
    concepts_missed = state.get("concepts_missed", [])

    if verdict == "MASTERED":
        return "advance"
    elif attempt >= MAX_ATTEMPTS:
        return "flag_review"
    elif attempt >= 3 and len(concepts_missed) > 0:
        return "recommend_prereqs"
    else:
        return "reteach"


# ─── Graph construction ────────────────────────────────────────────────────────

def build_teaching_graph():
    graph = StateGraph(TeachingState)

    graph.add_node("teach", teaching_node)
    graph.add_node("validate", validator_node)
    graph.add_node("recommend_prereqs", prereq_recommendation_node)
    graph.add_node("reteach", reteach_node)
    graph.add_node("advance", advance_node)
    graph.add_node("flag_review", flag_review_node)

    graph.set_entry_point("teach")

    # After teach: pause, await student explanation
    graph.add_edge("teach", END)

    # After validation: route based on verdict + attempt count
    graph.add_conditional_edges("validate", route_after_validation, {
        "advance": "advance",
        "reteach": "reteach",
        "recommend_prereqs": "recommend_prereqs",
        "flag_review": "flag_review",
    })

    graph.add_edge("recommend_prereqs", "reteach")
    graph.add_edge("reteach", END)   # pause again, await next explanation
    graph.add_edge("advance", END)
    graph.add_edge("flag_review", END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# Singleton compiled graph
teaching_graph = build_teaching_graph()


def get_thread_id(student_id: str, module_id: str) -> str:
    """Thread ID for LangGraph checkpointing."""
    return f"{student_id}__{module_id}"


async def run_teach(state: TeachingState) -> dict:
    """Run initial teach node. Returns updated state."""
    thread_id = get_thread_id(state["student_id"], state["module_id"])
    config = {"configurable": {"thread_id": thread_id}}
    result = await teaching_graph.ainvoke(state, config=config)
    return result


async def run_validate(state: TeachingState) -> dict:
    """Resume graph from validate node with student's explanation."""
    thread_id = get_thread_id(state["student_id"], state["module_id"])
    config = {"configurable": {"thread_id": thread_id}}
    result = await teaching_graph.ainvoke(state, config=config)
    return result
