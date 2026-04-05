"""
api/routes/teach.py
Teaching session endpoints using LangGraph with MemorySaver checkpointing.

Flow:
  POST /api/teach/start   → runs teach node, streams explanation via SSE
  POST /api/teach/explain → submits student explanation, runs validate → route
  GET  /api/teach/{session_id}/history → full attempt history
"""
from __future__ import annotations
import asyncio, json, os, uuid, time
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.db import supabase_query
from agents.teaching_agent import teach_concept
from agents.validator_agent import validate_explanation, P_INIT
from agents.input_filter import filter_student_input
from agents.student_memory import get_student_memory
from graph.graph import (
    teaching_graph, get_thread_id,
    teaching_node, validator_node, reteach_node, advance_node,
    flag_review_node, route_after_validation
)

router = APIRouter(prefix="/api/teach", tags=["teach"])

MAX_ATTEMPTS = 5
STRATEGY_MAP = {1: "direct", 2: "analogy", 3: "example", 4: "decompose"}

# In-memory session store with expiry (2 hours)
_sessions: dict[str, dict] = {}

def get_session(session_id: str) -> dict | None:
    entry = _sessions.get(session_id)
    if not entry:
        return None
    # Handle old format (dict without 'state' wrapper) gracefully
    if "state" not in entry:
        return entry  # legacy format — return directly
    if time.time() - entry.get("created_at", time.time()) > 7200:
        del _sessions[session_id]
        return None
    return entry["state"]

def set_session(session_id: str, state: dict):
    _sessions[session_id] = {"state": state, "created_at": time.time()}


# ─── Models ───────────────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    student_id: str
    module_id: str

class StartSessionResponse(BaseModel):
    session_id: str
    student_id: str
    module_id: str
    attempt_number: int
    mastery_score: float
    recommended_strategy: str
    prior_mastery: float
    concept_index: int = 0
    total_concepts: int = 1
    current_concept_title: str = ""

class ExplainRequest(BaseModel):
    explanation: str

class ExplainResponse(BaseModel):
    session_id: str
    attempt_number: int
    verdict: str                    # MASTERED | PARTIAL | NOT_YET | INVALID_INPUT
    pain_point: str
    feedback_to_student: str
    concepts_missed: list[str]
    scores: dict[str, float]
    mastery_probability: float
    mastery_score: float            # same as mastery_probability, for frontend compat
    advance: bool
    next_action: str                # "advance" | "reteach" | "recommend_prereqs" | "flag_review"
    prerequisite_modules: list[dict]
    next_strategy: str | None
    what_they_got_right: str = ""
    concept_index: int = 0
    total_concepts: int = 1
    concept_complete: bool = False
    prerequisite_recommendations: list[dict] = []
    # Legacy compat
    overall_score: float = 0.0
    feedback: str = ""

class AttemptOut(BaseModel):
    id: str
    attempt_number: int
    student_explanation: str
    validator_scores: dict[str, Any]
    mastery_probability: float
    created_at: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_module_with_chunks(module_id: str) -> tuple[dict, list[str]]:
    modules = await supabase_query(
        "modules",
        params={"id": f"eq.{module_id}", "select": "id,title,description,learning_objectives,source_chunk_ids,course_id"},
    )
    if not modules:
        raise HTTPException(status_code=404, detail=f"Module {module_id} not found.")
    module = modules[0]

    source_chunk_ids = module.get("source_chunk_ids") or []
    source_chunks: list[str] = []
    if source_chunk_ids:
        try:
            id_list = "(" + ",".join(str(i) for i in source_chunk_ids[:20]) + ")"
            chunks = await supabase_query(
                "chunks",
                params={"id": f"in.{id_list}", "select": "content,chunk_index"},
            )
            chunks_sorted = sorted(chunks, key=lambda c: c.get("chunk_index", 0))
            source_chunks = [c["content"] for c in chunks_sorted]
        except Exception:
            pass

    return module, source_chunks


async def _sse_stream(text: str) -> AsyncGenerator[str, None]:
    """Stream text word by word as SSE events."""
    words = text.split(" ")
    for i, word in enumerate(words):
        token = word if i == len(words) - 1 else word + " "
        yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
        await asyncio.sleep(0.02)
    yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest) -> StartSessionResponse:
    """Start a teaching session. Returns session_id and recommended strategy."""
    student_id = body.student_id
    module_id = body.module_id

    # Validate student
    students = await supabase_query("students", params={"id": f"eq.{student_id}", "select": "id,name"})
    if not students:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found.")

    # Get module + source chunks
    module, source_chunks = await _get_module_with_chunks(module_id)

    # Check for existing active session for this student + module
    # If one exists and isn't expired, resume it instead of creating a new one
    try:
        existing_sessions = await supabase_query(
            "sessions",
            params={
                "student_id": f"eq.{student_id}",
                "module_id": f"eq.{module_id}",
                "completed_at": "is.null",
                "select": "id,mastery_score",
            }
        )
    except Exception:
        existing_sessions = []

    # Get student memory for personalization
    memory = await get_student_memory(student_id, module_id)
    prior_mastery = memory.get("prior_mastery", 0.0)
    recommended_strategy = memory.get("recommended_strategy", "direct")
    attempt_count = memory.get("attempt_count", 0)

    # Resume existing session if available and still in memory
    if existing_sessions:
        existing_id = existing_sessions[0]["id"]
        existing_state = get_session(existing_id)
        if existing_state:
            # Session is live in memory — resume it
            concepts = module.get("concepts", [])
            total_concepts = len(concepts) if concepts else 1
            concept_index = existing_state.get("concept_index", 0)
            current_concept_title = ""
            if concepts and concept_index < len(concepts):
                current_concept_title = concepts[concept_index].get("title", "")
            return StartSessionResponse(
                session_id=existing_id,
                student_id=student_id,
                module_id=module_id,
                attempt_number=existing_state.get("attempt_number", 1),
                mastery_score=existing_state.get("mastery_probability", prior_mastery),
                recommended_strategy=existing_state.get("teaching_strategy", recommended_strategy),
                prior_mastery=existing_state.get("mastery_probability", prior_mastery),
                concept_index=concept_index,
                total_concepts=total_concepts,
                current_concept_title=current_concept_title,
            )
        # Session exists in DB but not memory — use its mastery score
        prior_mastery = existing_sessions[0].get("mastery_score", prior_mastery) or prior_mastery
        session_id = existing_id
        # Re-register in DB (update rather than insert)
        await supabase_query(
            f"sessions?id=eq.{session_id}",
            method="PATCH",
            json={"mastery_score": prior_mastery},
        )
    else:
        # Create new DB session
        session_id = str(uuid.uuid4())
        await supabase_query("sessions", method="POST", json={
            "id": session_id,
            "student_id": student_id,
            "module_id": module_id,
            "mastery_score": prior_mastery,
        })

    # Build initial LangGraph state
    # Get concepts from module
    concepts = module.get("concepts", [])
    total_concepts = len(concepts) if concepts else 1

    initial_state = {
        "session_id": session_id,
        "student_id": student_id,
        "module_id": module_id,
        "module": module,
        "source_chunks": source_chunks,
        "attempt_number": 1,
        "teaching_strategy": recommended_strategy,
        "mastery_probability": prior_mastery,
        "student_history": [],
        "pain_points": [],
        "concepts_missed": [],
        "prerequisite_modules": [],
        "pain_point": "",
        "should_advance": False,
        "should_flag": False,
        "concept_index": 0,
        "total_concepts": total_concepts,
    }

    # Run teach node via graph
    thread_id = get_thread_id(student_id, module_id)
    config = {"configurable": {"thread_id": thread_id}}
    result = await teaching_graph.ainvoke(initial_state, config=config)

    # Store session state
    s = dict(result)
    s["module"] = module
    s["source_chunks"] = source_chunks
    set_session(session_id, s)

    current_concept_title = ""
    if concepts and len(concepts) > 0:
        current_concept_title = concepts[0].get("title", "")

    return StartSessionResponse(
        session_id=session_id,
        student_id=student_id,
        module_id=module_id,
        attempt_number=1,
        mastery_score=prior_mastery,
        recommended_strategy=recommended_strategy,
        prior_mastery=prior_mastery,
        concept_index=0,
        total_concepts=total_concepts,
        current_concept_title=current_concept_title,
    )


@router.get("/{session_id}/explain")
async def stream_explanation(
    session_id: str,
    strategy: str = Query(default=None),
) -> StreamingResponse:
    """SSE stream of the current teaching explanation."""
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found. It may have expired. Start a new session.")

    # If strategy override provided, regenerate
    if strategy and strategy != state.get("teaching_strategy"):
        state["teaching_strategy"] = strategy

    explanation = state.get("current_explanation", "")

    # If no explanation yet (shouldn't happen), generate one
    if not explanation:
        try:
            explanation = await teach_concept(
                module=state.get("module", {}),
                student_history=state.get("student_history", []),
                source_chunks=state.get("source_chunks", []),
                strategy=state.get("teaching_strategy", "direct"),
                pain_point=state.get("pain_point", ""),
                attempt_number=state.get("attempt_number", 1),
                concept_index=state.get("concept_index", 0),
            )
            state["current_explanation"] = explanation
            set_session(session_id, state)
        except Exception as e:
            explanation = f"Error generating explanation: {str(e)}"

    return StreamingResponse(_sse_stream(explanation), media_type="text/event-stream")


@router.post("/{session_id}/submit", response_model=ExplainResponse)
async def submit_explanation(session_id: str, body: ExplainRequest) -> ExplainResponse:
    """Submit student explanation. Runs validate → route in LangGraph."""
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found. It may have expired. Start a new session.")

    student_id = state["student_id"]
    module_id = state["module_id"]
    attempt_number = state.get("attempt_number", 1)

    # PRE-FILTER — runs before any LLM call, no attempt counted
    # Skip filter for MCQ-style inputs (start with "Selected:")
    if not body.explanation.startswith("Selected:"):
        filter_result = filter_student_input(body.explanation)
        if not filter_result["is_valid"]:
            current_mastery = state.get("mastery_probability", 0.0)
            return ExplainResponse(
                session_id=session_id,
                attempt_number=attempt_number,  # NOT incremented
                verdict="INVALID_INPUT",
                pain_point="",
                feedback_to_student=filter_result["rejection_reason"],
                concepts_missed=[],
                scores={},
                mastery_probability=current_mastery,
                mastery_score=current_mastery,
                advance=False,
                next_action="explain_back",
                prerequisite_modules=[],
                next_strategy=None,
                overall_score=0.0,
                feedback=filter_result["rejection_reason"],
                what_they_got_right="",
            )

    # Get agent's last explanation for reference-anchored validation
    agent_explanation = state.get("current_explanation", "")

    # Call validator DIRECTLY — no LangGraph, no state-mangling
    prior_mastery = state.get("mastery_probability", 0.0)
    result = await validate_explanation(
        student_explanation=body.explanation,
        module=state.get("module", {}),
        source_chunks=state.get("source_chunks", []),
        prior_mastery=prior_mastery,
        attempt_number=attempt_number,
        agent_explanation=agent_explanation,
    )

    verdict = result["verdict"]
    mastery = result["mastery_score"]
    feedback = result.get("feedback_to_student", "")
    scores = result.get("scores", {})

    # Determine next action
    if verdict == "MASTERED":
        next_action = "advance"
        new_attempt = attempt_number  # no increment on success
    elif verdict == "INVALID_INPUT":
        next_action = "explain_back"
        new_attempt = attempt_number  # no increment for invalid input
    elif attempt_number >= MAX_ATTEMPTS:
        next_action = "flag_review"
        new_attempt = attempt_number + 1
    else:
        next_action = "reteach"
        new_attempt = attempt_number + 1

    should_advance = verdict == "MASTERED"
    should_flag = next_action == "flag_review"

    # Update session state
    state["mastery_probability"] = mastery
    state["mastery_score"] = mastery
    state["attempt_number"] = new_attempt
    state["last_verdict"] = verdict
    state["pain_point"] = result.get("pain_point", "")
    if verdict not in ("MASTERED", "INVALID_INPUT"):
        pain_points = list(state.get("pain_points", []))
        if result.get("pain_point"):
            pain_points.append(result["pain_point"])
        state["pain_points"] = pain_points

    # Persist session
    if not should_advance and not should_flag:
        set_session(session_id, state)
    else:
        _sessions.pop(session_id, None)

    # Persist to DB (non-blocking, skip for invalid input)
    if verdict != "INVALID_INPUT":
        try:
            await supabase_query("kc_attempts", method="POST", json={
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "module_id": module_id,
                "student_explanation": body.explanation,
                "validator_scores": {
                    **scores,
                    "verdict": verdict,
                    "pain_point": result.get("pain_point", ""),
                    "understanding_score": result.get("understanding_score", 5),
                },
                "mastery_probability": mastery,
                "attempt_number": attempt_number,
            })
        except Exception:
            pass
        try:
            update_payload: dict[str, Any] = {"mastery_score": mastery}
            if should_advance or should_flag:
                from datetime import datetime, timezone
                update_payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            if should_flag:
                update_payload["notes"] = "; ".join(state.get("pain_points", []))
            await supabase_query(f"sessions?id=eq.{session_id}", method="PATCH", json=update_payload)
        except Exception:
            pass

    # Handle concept advancement within a module
    concept_index = state.get("concept_index", 0)
    total_concepts = state.get("total_concepts", 1)
    concept_complete = False
    prereq_recs = []

    if verdict == "MASTERED":
        # Advance to next concept within module
        next_concept_index = concept_index + 1
        state["concept_index"] = next_concept_index
        state["attempt_number"] = 1  # reset attempts for new concept
        state["pain_point"] = ""
        state["student_history"] = []

        concept_complete = next_concept_index >= total_concepts

        if concept_complete:
            # All concepts in module done — advance to next module
            next_action = "advance"
        else:
            # More concepts to teach — reteach next concept
            next_action = "next_concept"
            should_advance = False

        if not concept_complete:
            set_session(session_id, state)

    elif should_flag and attempt_number >= 3:
        # Student struggling after 3+ attempts — surface prerequisites
        try:
            from agents.grading_agent import compute_learning_curve_score
            module_obj = state.get("module", {})
            concepts_missed = result.get("concepts_missed", [])
            if concepts_missed:
                from groq import Groq as _G
                gc = _G(api_key=os.getenv("GROQ_API_KEY"))
                pr = gc.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": f"""The student is struggling with: {module_obj.get('title', '')}
They are missing: {concepts_missed}

Suggest 2 prerequisite topics that would help. Return JSON:
{{"recommendations": [{{"topic": "...", "reason": "one sentence why this helps", "brief_explanation": "2-3 sentences"}}]}}"""}],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    max_tokens=300,
                )
                pr_data = __import__("json").loads(pr.choices[0].message.content)
                prereq_recs = pr_data.get("recommendations", [])
                state["prerequisite_modules"] = prereq_recs
                set_session(session_id, state)
        except Exception:
            pass

    return ExplainResponse(
        session_id=session_id,
        attempt_number=new_attempt,
        verdict=verdict,
        pain_point=result.get("pain_point", ""),
        feedback_to_student=feedback,
        concepts_missed=result.get("concepts_missed", []),
        scores=scores,
        mastery_probability=mastery,
        advance=should_advance,
        next_action=next_action,
        prerequisite_modules=state.get("prerequisite_modules", []),
        next_strategy=result.get("next_strategy"),
        overall_score=result.get("overall_score", 0.0),
        feedback=feedback,
        mastery_score=mastery,
        what_they_got_right=result.get("what_they_got_right", ""),
        concept_index=state.get("concept_index", concept_index),
        total_concepts=total_concepts,
        concept_complete=concept_complete,
        prerequisite_recommendations=prereq_recs,
    )


@router.get("/{session_id}/history", response_model=list[AttemptOut])
async def get_session_history(session_id: str) -> list[AttemptOut]:
    """Return full attempt history for a session."""
    history = await supabase_query(
        "kc_attempts",
        params={"session_id": f"eq.{session_id}", "select": "id,attempt_number,student_explanation,validator_scores,mastery_probability,created_at"},
    )
    return [
        AttemptOut(
            id=h["id"],
            attempt_number=h.get("attempt_number", 0),
            student_explanation=h.get("student_explanation", ""),
            validator_scores=h.get("validator_scores") or {},
            mastery_probability=h.get("mastery_probability", 0.0),
            created_at=h.get("created_at", ""),
        )
        for h in history
    ]
