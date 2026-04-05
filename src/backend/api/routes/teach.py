"""
api/routes/teach.py
Adaptive teaching session endpoints with SSE streaming.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.db import supabase_query
from agents.teaching_agent import teach_concept
from agents.validator_agent import validate_explanation, P_INIT
from agents.grading_agent import grade_explanation
from agents.student_memory import get_student_memory

# Teaching strategy rotation order (matches graph/graph.py)
STRATEGY_ROTATION = ["simplified", "analogy", "worked_example"]

router = APIRouter(prefix="/api/teach", tags=["teach"])

# Maximum explain-back attempts per session
MAX_ATTEMPTS = 3


# ─────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    student_id: str
    module_id: str


class StartSessionResponse(BaseModel):
    session_id: str
    student_id: str
    module_id: str
    attempt_count: int
    mastery_score: float
    recommended_strategy: str = "initial"
    prior_mastery: float = 0.3
    attempt_count_history: int = 0


class SubmitRequest(BaseModel):
    student_explanation: str


class SubmitResponse(BaseModel):
    attempt_number: int
    scores: dict[str, float]
    overall_score: float
    mastery_probability: float
    feedback: str
    advance: bool
    next_strategy: str | None
    # Grading fields
    grade_letter: str | None = None
    correct_points: list[str] = []
    incorrect_points: list[str] = []
    missing_points: list[str] = []
    accuracy_score: float | None = None
    completeness_score: float | None = None
    learning_verdict: str | None = None


class AttemptOut(BaseModel):
    id: str
    attempt_number: int
    student_explanation: str
    validator_scores: dict[str, Any]
    mastery_probability: float
    created_at: str


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

async def _get_session(session_id: str) -> dict[str, Any]:
    """Fetch a session record; raise 404 if not found."""
    sessions = await supabase_query(
        "sessions",
        params={
            "id": f"eq.{session_id}",
            "select": "id,student_id,module_id,mastery_score,completed_at",
        },
    )
    if not sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")
    return sessions[0]


async def _get_module_with_chunks(module_id: str) -> tuple[dict[str, Any], list[str]]:
    """
    Fetch a module and its associated source chunk texts.

    Returns:
        (module_dict, list_of_chunk_texts)
    """
    modules = await supabase_query(
        "modules",
        params={
            "id": f"eq.{module_id}",
            "select": "id,title,description,learning_objectives,source_chunk_ids",
        },
    )
    if not modules:
        raise HTTPException(status_code=404, detail=f"Module {module_id} not found.")
    module = modules[0]

    chunk_ids: list[str] = module.get("source_chunk_ids") or []
    source_chunks: list[str] = []

    if chunk_ids:
        id_list = "(" + ",".join(chunk_ids) + ")"
        chunks_raw = await supabase_query(
            "chunks",
            params={
                "id": f"in.{id_list}",
                "select": "content,chunk_index",
                "order": "chunk_index.asc",
            },
        )
        source_chunks = [c["content"] for c in chunks_raw]

    return module, source_chunks


async def _get_session_history(session_id: str) -> list[dict[str, Any]]:
    """Fetch ordered attempt history for a session."""
    attempts = await supabase_query(
        "kc_attempts",
        params={
            "session_id": f"eq.{session_id}",
            "select": "id,attempt_number,student_explanation,validator_scores,mastery_probability,created_at",
            "order": "attempt_number.asc",
        },
    )
    return attempts or []


async def _current_attempt_count(session_id: str) -> int:
    """Return the number of kc_attempts for a session."""
    rows = await supabase_query(
        "kc_attempts",
        params={"session_id": f"eq.{session_id}", "select": "id"},
    )
    return len(rows)


def _pick_strategy(attempt_count: int) -> str:
    """Pick a teaching strategy based on how many attempts have been made."""
    if attempt_count == 0:
        return "initial"
    rotation_index = min(attempt_count - 1, len(STRATEGY_ROTATION) - 1)
    return STRATEGY_ROTATION[rotation_index]


async def _sse_event_generator(
    explanation_text: str,
    chunk_size: int = 20,
) -> AsyncGenerator[str, None]:
    """
    Yield an explanation as SSE events, simulating token-by-token streaming.

    Each event sends a small word chunk followed by a final [DONE] event.
    """
    words = explanation_text.split()
    buffer: list[str] = []

    for word in words:
        buffer.append(word)
        if len(buffer) >= chunk_size:
            chunk = " ".join(buffer) + " "
            payload = json.dumps({"token": chunk, "done": False})
            yield f"data: {payload}\n\n"
            buffer = []
            await asyncio.sleep(0.01)  # Brief yield to avoid blocking

    # Flush remaining
    if buffer:
        chunk = " ".join(buffer)
        payload = json.dumps({"token": chunk, "done": False})
        yield f"data: {payload}\n\n"
        await asyncio.sleep(0.01)

    # Final event
    yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@router.post("/start", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest) -> StartSessionResponse:
    """
    Start a teaching session for a student on a specific module.

    Creates a new session record and returns the session_id.
    """
    student_id = body.student_id
    module_id = body.module_id

    # Verify student exists
    students = await supabase_query(
        "students",
        params={"id": f"eq.{student_id}", "select": "id"},
    )
    if not students:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found.")

    # Verify module exists
    modules = await supabase_query(
        "modules",
        params={"id": f"eq.{module_id}", "select": "id"},
    )
    if not modules:
        raise HTTPException(status_code=404, detail=f"Module {module_id} not found.")

    # Get student memory for personalization
    memory = await get_student_memory(student_id, module_id)

    # Create session
    session_id = str(uuid.uuid4())
    await supabase_query(
        "sessions",
        method="POST",
        json={
            "id": session_id,
            "student_id": student_id,
            "module_id": module_id,
            "mastery_score": 0.0,
        },
    )

    return StartSessionResponse(
        session_id=session_id,
        student_id=student_id,
        module_id=module_id,
        attempt_count=0,
        mastery_score=0.0,
        recommended_strategy=memory["recommended_strategy"],
        prior_mastery=memory["prior_mastery"],
        attempt_count_history=memory["attempt_count"],
    )


@router.get("/{session_id}/explain")
async def stream_explanation(
    session_id: str,
    strategy: str | None = Query(default=None, description="Teaching strategy override"),
) -> StreamingResponse:
    """
    SSE streaming endpoint for the teaching explanation.

    Generates a teaching explanation based on current session state
    and streams it token-by-token using Server-Sent Events.

    Accepts an optional `strategy` query parameter to override the
    automatic strategy selection. Valid values: initial, simplified,
    analogy, worked_example.
    """
    session = await _get_session(session_id)

    if session.get("completed_at"):
        raise HTTPException(status_code=400, detail="Session already completed.")

    module, source_chunks = await _get_module_with_chunks(session["module_id"])
    history = await _get_session_history(session_id)
    attempt_count = len(history)

    # Use provided strategy if valid, otherwise auto-pick
    valid_strategies = {"initial", "simplified", "analogy", "worked_example"}
    if strategy and strategy in valid_strategies:
        pass  # use the provided strategy
    else:
        strategy = _pick_strategy(attempt_count)

    # Build student history in the format expected by teaching_agent
    student_history = [
        {
            "attempt_number": h.get("attempt_number"),
            "student_explanation": h.get("student_explanation", ""),
            "validator_scores": h.get("validator_scores", {}),
            "mastery_probability": h.get("mastery_probability", 0.0),
        }
        for h in history
    ]

    # Fetch student memory for context injection
    try:
        memory = await get_student_memory(session["student_id"], session["module_id"])
        memory_context = memory.get("memory_context", "")
    except Exception:
        memory_context = ""

    # Prepend memory context as an additional source chunk if present
    enriched_chunks = list(source_chunks)
    if memory_context:
        enriched_chunks = [memory_context] + enriched_chunks

    # Generate explanation
    try:
        explanation = await teach_concept(
            module=module,
            student_history=student_history,
            source_chunks=enriched_chunks,
            strategy=strategy,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return StreamingResponse(
        _sse_event_generator(explanation),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{session_id}/submit", response_model=SubmitResponse)
async def submit_explanation(session_id: str, body: SubmitRequest) -> SubmitResponse:
    """
    Submit the student's explain-back text for validation.

    - Runs the 4-dimension validator
    - Applies BKT mastery update
    - Stores the attempt in kc_attempts
    - Updates session mastery_score
    - Marks session completed if advancing
    """
    session = await _get_session(session_id)

    if session.get("completed_at"):
        raise HTTPException(status_code=400, detail="Session already completed.")

    module, source_chunks = await _get_module_with_chunks(session["module_id"])
    history = await _get_session_history(session_id)
    attempt_count = len(history)
    next_attempt_number = attempt_count + 1

    # Get prior mastery (from last attempt or session default)
    prior_mastery = (
        history[-1].get("mastery_probability", P_INIT)
        if history
        else session.get("mastery_score", P_INIT)
    )

    # Validate explanation
    try:
        result = await validate_explanation(
            student_explanation=body.student_explanation,
            module=module,
            source_chunks=source_chunks,
            prior_mastery=prior_mastery,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Store kc_attempt
    attempt_id = str(uuid.uuid4())
    await supabase_query(
        "kc_attempts",
        method="POST",
        json={
            "id": attempt_id,
            "session_id": session_id,
            "module_id": session["module_id"],
            "student_explanation": body.student_explanation,
            "validator_scores": result["scores"],
            "mastery_probability": result["mastery_probability"],
            "attempt_number": next_attempt_number,
        },
    )

    # Update session mastery score
    update_payload: dict[str, Any] = {"mastery_score": result["mastery_probability"]}
    should_advance = result["advance"] or next_attempt_number >= MAX_ATTEMPTS

    if should_advance:
        from datetime import datetime, timezone
        update_payload["completed_at"] = datetime.now(timezone.utc).isoformat()

    await supabase_query(
        f"sessions?id=eq.{session_id}",
        method="PATCH",
        json=update_payload,
    )

    # Determine next strategy if not advancing
    next_strategy: str | None = None
    if not should_advance:
        rotation_index = min(next_attempt_number - 1, len(STRATEGY_ROTATION) - 1)
        next_strategy = STRATEGY_ROTATION[rotation_index]

    # Run grading agent to validate correctness against source material
    grade_result = {}
    try:
        grade_result = await grade_explanation(
            student_explanation=body.student_explanation,
            module=module,
            source_chunks=source_chunks,
        )
    except Exception:
        pass  # Grading is non-blocking

    return SubmitResponse(
        attempt_number=next_attempt_number,
        scores=result["scores"],
        overall_score=result["overall_score"],
        mastery_probability=result["mastery_probability"],
        feedback=result["feedback"],
        advance=should_advance,
        next_strategy=next_strategy,
        grade_letter=grade_result.get("grade_letter"),
        correct_points=grade_result.get("correct_points", []),
        incorrect_points=grade_result.get("incorrect_points", []),
        missing_points=grade_result.get("missing_points", []),
        accuracy_score=grade_result.get("accuracy_score"),
        completeness_score=grade_result.get("completeness_score"),
        learning_verdict=grade_result.get("learning_verdict"),
    )


@router.get("/{session_id}/history", response_model=list[AttemptOut])
async def get_session_history(session_id: str) -> list[AttemptOut]:
    """
    Return the full attempt history for a teaching session.
    """
    # Verify session exists
    await _get_session(session_id)

    history = await _get_session_history(session_id)

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
