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

class ExplainRequest(BaseModel):
    explanation: str

class ExplainResponse(BaseModel):
    session_id: str
    attempt_number: int
    verdict: str                    # MASTERED | PARTIAL | NOT_YET
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

    # Get student memory for personalization
    memory = await get_student_memory(student_id, module_id)
    prior_mastery = memory.get("prior_mastery", P_INIT)
    recommended_strategy = memory.get("recommended_strategy", "direct")
    attempt_count = memory.get("attempt_count", 0)

    # Create DB session
    session_id = str(uuid.uuid4())
    await supabase_query("sessions", method="POST", json={
        "id": session_id,
        "student_id": student_id,
        "module_id": module_id,
        "mastery_score": prior_mastery,
    })

    # Build initial LangGraph state
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

    return StartSessionResponse(
        session_id=session_id,
        student_id=student_id,
        module_id=module_id,
        attempt_number=1,
        mastery_score=prior_mastery,
        recommended_strategy=recommended_strategy,
        prior_mastery=prior_mastery,
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

    # Update state with student response
    state["student_response"] = body.explanation
    # Pass agent explanation for reference-anchored validation
    state["agent_explanation"] = state.get("current_explanation", "")

    # Run validate → route via graph
    thread_id = get_thread_id(student_id, module_id)
    config = {"configurable": {"thread_id": thread_id}}
    result = await teaching_graph.ainvoke(state, config=config)

    # Determine next action from routing
    next_action = route_after_validation(result)

    # Persist attempt to DB
    attempt_id = str(uuid.uuid4())
    try:
        await supabase_query("kc_attempts", method="POST", json={
            "id": attempt_id,
            "session_id": session_id,
            "module_id": module_id,
            "student_explanation": body.explanation,
            "validator_scores": {
                **result.get("scores", {}),
                "verdict": result.get("last_verdict", "NOT_YET"),
                "pain_point": result.get("pain_point", ""),
                "concepts_missed": result.get("concepts_missed", []),
            },
            "mastery_probability": result.get("mastery_probability", 0.3),
            "attempt_number": attempt_number,
        })
    except Exception:
        pass

    # Update session mastery
    should_advance = result.get("should_advance", False)
    should_flag = result.get("should_flag", False)
    update_payload: dict[str, Any] = {"mastery_score": result.get("mastery_probability", 0.3)}

    if should_advance or should_flag:
        from datetime import datetime, timezone
        update_payload["completed_at"] = datetime.now(timezone.utc).isoformat()

    if should_flag:
        # Aggregate pain points for professor
        pain_summary = "; ".join(result.get("pain_points", []))
        update_payload["notes"] = pain_summary

    try:
        await supabase_query(f"sessions?id=eq.{session_id}", method="PATCH", json=update_payload)
    except Exception:
        pass

    # Update in-memory session for next turn
    if not should_advance and not should_flag:
        s = dict(result)
        s["module"] = state["module"]
        s["source_chunks"] = state["source_chunks"]
        set_session(session_id, s)
    else:
        _sessions.pop(session_id, None)

    verdict = result.get("last_verdict", "NOT_YET")
    mastery = result.get("mastery_probability", 0.3)
    feedback = result.get("feedback_to_student", "")
    scores = result.get("scores", {})
    overall = sum(scores.values()) / len(scores) if scores else 0.0

    return ExplainResponse(
        session_id=session_id,
        attempt_number=attempt_number,
        verdict=verdict,
        pain_point=result.get("pain_point", ""),
        feedback_to_student=feedback,
        concepts_missed=result.get("concepts_missed", []),
        scores=scores,
        mastery_probability=mastery,
        advance=should_advance,
        next_action=next_action,
        prerequisite_modules=result.get("prerequisite_modules", []),
        next_strategy=result.get("teaching_strategy"),
        overall_score=round(overall, 3),
        feedback=feedback,
        mastery_score=mastery,
        what_they_got_right=result.get("what_they_got_right", ""),
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
