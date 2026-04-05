"""
graph/graph.py
LangGraph StateGraph for the adaptive teaching loop.

Flow:
  teach → wait_for_response → validate → decide
                                 ↑              |
                                 └──── reteach ←┘ (if not advancing)

The graph is compiled once at module load time and reused across requests.
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END

from graph.state import TeachingState
from agents.teaching_agent import teach_concept
from agents.validator_agent import validate_explanation

# Maximum number of explain-back attempts before forcing advancement
MAX_ATTEMPTS = 3

# Strategy rotation order after the initial attempt
STRATEGY_ROTATION = ["simplified", "analogy", "worked_example"]


# ─────────────────────────────────────────────────────────
# Node implementations
# ─────────────────────────────────────────────────────────

async def teach_node(state: TeachingState) -> dict[str, Any]:
    """
    Generate a teaching explanation using the current strategy.
    Updates current_explanation in state.
    """
    explanation = await teach_concept(
        module={"module_id": state["module_id"]},  # Minimal; routes fill module fully
        student_history=state["student_history"],
        source_chunks=state["source_chunks"],
        strategy=state["strategy"],
    )
    return {"current_explanation": explanation}


async def wait_for_response_node(state: TeachingState) -> dict[str, Any]:
    """
    Passthrough node that signals the graph is waiting for student input.
    In the API layer, the graph is interrupted here and resumed after the
    student submits their explain-back via POST /api/teach/{session_id}/submit.
    Returns state unchanged (the actual student_response is injected externally).
    """
    # This node is a logical checkpoint — no transformation needed.
    return {}


async def validate_node(state: TeachingState) -> dict[str, Any]:
    """
    Validate the student's explain-back using the rubric validator.
    Updates validator_result, mastery_probability, and attempt_count.
    """
    student_response = state.get("student_response") or ""

    # Build a minimal module dict for the validator
    module = {"module_id": state["module_id"]}

    result = await validate_explanation(
        student_explanation=student_response,
        module=module,
        source_chunks=state["source_chunks"],
        prior_mastery=state["mastery_probability"],
    )

    new_attempt_count = state["attempt_count"] + 1

    # Build updated history entry
    history_entry: dict[str, Any] = {
        "attempt_number": new_attempt_count,
        "student_explanation": student_response,
        "validator_scores": result["scores"],
        "mastery_probability": result["mastery_probability"],
    }
    updated_history = list(state["student_history"]) + [history_entry]

    return {
        "validator_result": result,
        "mastery_probability": result["mastery_probability"],
        "attempt_count": new_attempt_count,
        "student_history": updated_history,
    }


async def decide_node(state: TeachingState) -> dict[str, Any]:
    """
    Decide whether to advance the student or reteach with a new strategy.

    Advances if:
      - mastery_probability >= 0.8, OR
      - attempt_count >= MAX_ATTEMPTS

    Reteaches if neither condition is met, rotating through strategies.
    """
    mastery = state["mastery_probability"]
    attempts = state["attempt_count"]

    if mastery >= 0.8 or attempts >= MAX_ATTEMPTS:
        return {"should_advance": True}

    # Pick next strategy (rotate through the list)
    rotation_index = min(attempts - 1, len(STRATEGY_ROTATION) - 1)
    next_strategy = STRATEGY_ROTATION[rotation_index]

    return {
        "should_advance": False,
        "strategy": next_strategy,
        "student_response": None,  # Reset for next round
    }


# ─────────────────────────────────────────────────────────
# Conditional edge
# ─────────────────────────────────────────────────────────

def route_after_decide(state: TeachingState) -> str:
    """Route to 'teach' for reteaching or END for advancement."""
    if state.get("should_advance"):
        return END
    return "teach"


# ─────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────

def build_teaching_graph() -> Any:
    """
    Build and compile the LangGraph StateGraph for the teaching loop.

    Returns:
        Compiled LangGraph runnable.
    """
    builder = StateGraph(TeachingState)

    # Register nodes
    builder.add_node("teach", teach_node)
    builder.add_node("wait_for_response", wait_for_response_node)
    builder.add_node("validate", validate_node)
    builder.add_node("decide", decide_node)

    # Define edges
    builder.set_entry_point("teach")
    builder.add_edge("teach", "wait_for_response")
    builder.add_edge("wait_for_response", "validate")
    builder.add_edge("validate", "decide")
    builder.add_conditional_edges(
        "decide",
        route_after_decide,
        {
            "teach": "teach",
            END: END,
        },
    )

    return builder.compile()


# Module-level compiled graph (singleton)
teaching_graph = build_teaching_graph()


async def run_teaching_turn(state: TeachingState) -> TeachingState:
    """
    Run a single turn of the teaching loop.

    In a streaming / interrupt-based architecture, this runs one complete
    teach → validate → decide cycle given the current state (which already
    contains the student's response).

    Args:
        state: Current TeachingState with student_response populated.

    Returns:
        Updated TeachingState after one complete cycle.
    """
    result = await teaching_graph.ainvoke(state)
    return result
