"""
api/routes/teach.py
Teaching session endpoints using LangGraph with MemorySaver checkpointing.

Flow:
  POST /api/teach/start   → runs teach node, streams explanation via SSE
  POST /api/teach/explain → submits student explanation, runs validate → route
  GET  /api/teach/{session_id}/history → full attempt history
"""
from __future__ import annotations
import asyncio, json, uuid, time
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

# In-memory session store with expiry (24 hours — extended from 2h so
# navigating between modules within a day never loses state)
_sessions: dict[str, dict] = {}
SESSION_TTL = 86400  # 24 hours

def get_session(session_id: str) -> dict | None:
    entry = _sessions.get(session_id)
    if not entry:
        return None
    # Handle old format (dict without 'state' wrapper) gracefully
    if "state" not in entry:
        return entry  # legacy format — return directly
    if time.time() - entry.get("created_at", time.time()) > SESSION_TTL:
        del _sessions[session_id]
        return None
    return entry["state"]

def set_session(session_id: str, state: dict):
    _sessions[session_id] = {"state": state, "created_at": time.time()}


# ─── Confusion signal detection ───────────────────────────────────────────────

_CONFUSION_SIGNALS = [
    "i don't understand", "i dont understand",
    "i do not understand", "do not understand",
    "i don't get it", "i dont get it", "i do not get it",
    "i don't get this", "i dont get this", "i do not get this",
    "still don't get", "still dont get", "still do not get",
    "don't follow", "dont follow", "do not follow",
    "makes no sense", "doesn't make sense", "does not make sense",
    "confused", "confusing",
    "lost me", "im lost", "i'm lost", "i am lost",
    "what does that mean", "what do you mean",
    "can you explain", "explain again", "explain differently",
    "i have no idea", "no idea", "have no idea",
    "not getting it", "not understanding",
    "what?", "huh?",
]

def _is_confusion_signal(text: str) -> bool:
    t = text.lower().strip()
    return any(s in t for s in _CONFUSION_SIGNALS)


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
    next_action: str                # "advance" | "reteach" | "prereq_drill" | "resume_concept" | "flag_review"
    prerequisite_modules: list[dict]
    next_strategy: str | None
    what_they_got_right: str = ""
    concept_index: int = 0
    total_concepts: int = 1
    concept_complete: bool = False
    prerequisite_recommendations: list[dict] = []
    # Inline prereq drilling
    prereq_active: bool = False     # True while drilling a foundational gap inline
    prereq_concept: str = ""        # name of the gap being drilled
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
        params={"id": f"eq.{module_id}", "select": "id,title,description,learning_objectives,source_chunk_ids,course_id,concepts,estimated_minutes"},
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

    # Ensure concepts field exists as a list
    if "concepts" not in module or not module["concepts"]:
        module["concepts"] = []

    # Check for existing session for this student + module (active or completed).
    # Going back to a completed module should still show progress, not start fresh.
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

    # If no active session, check for a completed one (back-navigation case)
    if not existing_sessions:
        try:
            completed_sessions = await supabase_query(
                "sessions",
                params={
                    "student_id": f"eq.{student_id}",
                    "module_id": f"eq.{module_id}",
                    "select": "id,mastery_score,completed_at",
                }
            )
            if completed_sessions:
                # Pick the session with highest mastery score
                best = max(completed_sessions, key=lambda s: s.get("mastery_score") or 0)
                existing_sessions = [best]
        except Exception:
            pass

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
        # Session exists in DB but NOT in memory (expired or server restarted).
        # Rebuild full state from DB so the student picks up exactly where they left off.
        prior_mastery = existing_sessions[0].get("mastery_score", prior_mastery) or prior_mastery
        session_id = existing_id

        try:
            existing_attempts = await supabase_query(
                "kc_attempts",
                params={
                    "session_id": f"eq.{session_id}",
                    "select": "attempt_number,student_explanation,validator_scores,mastery_probability,created_at",
                    "order": "attempt_number.asc",
                }
            )
        except Exception:
            existing_attempts = []

        # Rebuild student_history from stored attempts
        rebuilt_history = [
            {
                "attempt_number": a.get("attempt_number", 1),
                "student_explanation": a.get("student_explanation", ""),
                "verdict": (a.get("validator_scores") or {}).get("verdict", "PARTIAL"),
                "pain_point": (a.get("validator_scores") or {}).get("pain_point", ""),
                "mastery_probability": a.get("mastery_probability", 0.0),
                "scores": {
                    k: v for k, v in (a.get("validator_scores") or {}).items()
                    if k not in ("verdict", "pain_point", "understanding_score")
                },
            }
            for a in existing_attempts
        ]

        # Determine concept_index: each MASTERED verdict advances one concept
        concepts = module.get("concepts", [])
        total_concepts = len(concepts) if concepts else 1
        concept_index = sum(1 for h in rebuilt_history if h["verdict"] == "MASTERED")
        concept_index = min(concept_index, total_concepts - 1)

        # Determine current attempt number within the current concept
        current_concept_attempts = [
            h for h in rebuilt_history
            if h["verdict"] not in ("MASTERED",)
        ]
        current_attempt = len(current_concept_attempts) % MAX_ATTEMPTS + 1 if current_concept_attempts else 1

        # Rebuild pain_points from history
        rebuilt_pain_points = [h["pain_point"] for h in rebuilt_history if h.get("pain_point")]

        rebuilt_state = {
            "session_id": session_id,
            "student_id": student_id,
            "module_id": module_id,
            "module": module,
            "source_chunks": source_chunks,
            "attempt_number": current_attempt,
            "teaching_strategy": recommended_strategy,
            "mastery_probability": prior_mastery,
            "student_history": rebuilt_history,
            "pain_points": rebuilt_pain_points,
            "pain_point": rebuilt_history[-1].get("pain_point", "") if rebuilt_history else "",
            "concepts_missed": [],
            "prerequisite_modules": [],
            "should_advance": False,
            "should_flag": False,
            "concept_index": concept_index,
            "total_concepts": total_concepts,
            "strategies_used": [],
            "explicit_confusion": False,
            "prereq_active": False,
            "prereq_concept": "",
            "prereq_explanation": "",
            "prereq_return_attempt": 1,
            "prereq_return_explanation": "",
            "consecutive_fails": 0,
            "current_explanation": "",
        }
        set_session(session_id, rebuilt_state)

        current_concept_title = ""
        if concepts and concept_index < len(concepts):
            current_concept_title = concepts[concept_index].get("title", "")

        return StartSessionResponse(
            session_id=session_id,
            student_id=student_id,
            module_id=module_id,
            attempt_number=current_attempt,
            mastery_score=prior_mastery,
            recommended_strategy=recommended_strategy,
            prior_mastery=prior_mastery,
            concept_index=concept_index,
            total_concepts=total_concepts,
            current_concept_title=current_concept_title,
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
        "strategies_used": [],
        "explicit_confusion": False,
        "prereq_active": False,
        "prereq_concept": "",
        "prereq_explanation": "",
        "prereq_return_attempt": 1,
        "prereq_return_explanation": "",
        "consecutive_fails": 0,
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

    # If no explanation yet (first load after DB reconstruct, or after confusion reset)
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
                strategies_used=state.get("strategies_used", []),
                explicit_confusion=state.get("explicit_confusion", False),
                pain_points=state.get("pain_points", []),
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

    # CONFUSION SIGNAL DETECTION — before any LLM call, no attempt counted.
    # If the student says "I don't understand" (or similar), skip the validator
    # entirely, flag explicit_confusion, change strategy, and regenerate explanation.
    if not body.explanation.startswith("Selected:") and _is_confusion_signal(body.explanation):
        # Mark confusion in session state — the next /explain will use a new strategy
        state["explicit_confusion"] = True
        strategies_used = list(state.get("strategies_used", []))
        current_strategy = state.get("teaching_strategy", "direct")
        from agents.teaching_agent import select_adaptive_strategy
        new_strategy = select_adaptive_strategy(
            attempt_number=attempt_number,
            strategies_used=strategies_used,
            explicit_confusion=True,
            pain_points=state.get("pain_points", []),
        )
        state["teaching_strategy"] = new_strategy
        # Regenerate explanation immediately with the new strategy
        new_explanation = await teach_concept(
            module=state.get("module", {}),
            student_history=state.get("student_history", []),
            source_chunks=state.get("source_chunks", []),
            strategy=new_strategy,
            pain_point=state.get("pain_point", ""),
            attempt_number=attempt_number,
            concept_index=state.get("concept_index", 0),
            strategies_used=strategies_used,
            explicit_confusion=True,
            pain_points=state.get("pain_points", []),
        )
        state["current_explanation"] = new_explanation
        if new_strategy not in strategies_used:
            strategies_used.append(new_strategy)
        state["strategies_used"] = strategies_used
        state["explicit_confusion"] = False
        set_session(session_id, state)
        current_mastery = state.get("mastery_probability", 0.0)
        # Return a special response — no attempt counted, new explanation ready
        return ExplainResponse(
            session_id=session_id,
            attempt_number=attempt_number,  # NOT incremented
            verdict="INVALID_INPUT",
            pain_point="",
            feedback_to_student="No problem — let me try explaining this a different way.",
            concepts_missed=[],
            scores={},
            mastery_probability=current_mastery,
            mastery_score=current_mastery,
            advance=False,
            next_action="reteach",
            prerequisite_modules=[],
            next_strategy=new_strategy,
            overall_score=0.0,
            feedback="No problem — let me try explaining this a different way.",
            what_they_got_right="",
            concept_index=state.get("concept_index", 0),
            total_concepts=state.get("total_concepts", 1),
            concept_complete=False,
        )

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

    # ── Read prereq drill state ───────────────────────────────────────────────
    prereq_active  = state.get("prereq_active", False)
    prereq_concept = state.get("prereq_concept", "")

    # ── Determine which module context to validate against ────────────────────
    # When drilling a prereq, validate against the prereq concept (synthetic module),
    # not the main concept, so the student isn't penalised for the original gap.
    if prereq_active and prereq_concept:
        validation_module = {
            "title": prereq_concept,
            "learning_objectives": [f"Explain {prereq_concept} in your own words"],
            "concepts": [{"title": prereq_concept,
                          "learning_objective": f"Explain {prereq_concept}"}],
        }
        validation_agent_explanation = state.get("prereq_explanation", "")
    else:
        validation_module = state.get("module", {})
        validation_agent_explanation = state.get("current_explanation", "")

    # ── Call validator ────────────────────────────────────────────────────────
    prior_mastery = state.get("mastery_probability", 0.0)
    result = await validate_explanation(
        student_explanation=body.explanation,
        module=validation_module,
        source_chunks=state.get("source_chunks", []),
        prior_mastery=prior_mastery,
        attempt_number=attempt_number,
        agent_explanation=validation_agent_explanation,
    )

    verdict = result["verdict"]
    mastery = result["mastery_score"]
    feedback = result.get("feedback_to_student", "")
    scores  = result.get("scores", {})

    # ── Prereq drill: check if student mastered the prerequisite ──────────────
    if prereq_active:
        if verdict == "MASTERED":
            # Prereq understood — exit drill mode and resume original concept
            print(f"[PREREQ_DRILL] '{prereq_concept}' mastered — resuming original concept")
            state["prereq_active"]  = False
            state["prereq_concept"] = ""
            state["consecutive_fails"] = 0
            state["attempt_number"] = state.get("prereq_return_attempt", 1)

            # Restore or regenerate the original concept explanation
            original_explanation = state.get("prereq_return_explanation", "")
            if not original_explanation:
                try:
                    original_explanation = await teach_concept(
                        module=state.get("module", {}),
                        student_history=state.get("student_history", []),
                        source_chunks=state.get("source_chunks", []),
                        strategy="direct",
                        pain_point="",
                        attempt_number=state.get("prereq_return_attempt", 1),
                        concept_index=state.get("concept_index", 0),
                    )
                except Exception:
                    original_explanation = ""
            state["current_explanation"] = original_explanation
            state["pain_point"] = ""
            set_session(session_id, state)

            return ExplainResponse(
                session_id=session_id,
                attempt_number=state.get("prereq_return_attempt", 1),
                verdict="MASTERED",
                pain_point="",
                feedback_to_student=f"You've got it! Now let's go back to the main concept.",
                concepts_missed=[],
                scores=scores,
                mastery_probability=mastery,
                mastery_score=mastery,
                advance=False,
                next_action="resume_concept",
                prerequisite_modules=[],
                next_strategy="direct",
                what_they_got_right=result.get("what_they_got_right", ""),
                concept_index=state.get("concept_index", 0),
                total_concepts=state.get("total_concepts", 1),
                concept_complete=False,
                prereq_active=False,
                prereq_concept="",
            )
        else:
            # Still not mastered — continue drilling the prereq
            print(f"[PREREQ_DRILL] '{prereq_concept}' not yet mastered — continuing drill")
            try:
                from agents.teaching_agent import select_adaptive_strategy as _sel
                drill_strat = _sel(
                    attempt_number=attempt_number + 1,
                    strategies_used=state.get("strategies_used", []),
                    explicit_confusion=False,
                    pain_points=[result.get("pain_point", "")],
                )
                drill_explanation = await teach_concept(
                    module={"title": prereq_concept, "description": prereq_concept,
                            "learning_objectives": [f"Explain {prereq_concept}"], "concepts": []},
                    student_history=[],
                    source_chunks=state.get("source_chunks", []),
                    strategy=drill_strat,
                    pain_point=result.get("pain_point", ""),
                    attempt_number=attempt_number + 1,
                )
                state["prereq_explanation"] = drill_explanation
                state["current_explanation"] = drill_explanation
            except Exception:
                pass
            state["attempt_number"] = attempt_number + 1
            set_session(session_id, state)

            return ExplainResponse(
                session_id=session_id,
                attempt_number=attempt_number + 1,
                verdict=verdict,
                pain_point=result.get("pain_point", ""),
                feedback_to_student=feedback,
                concepts_missed=result.get("concepts_missed", []),
                scores=scores,
                mastery_probability=mastery,
                mastery_score=mastery,
                advance=False,
                next_action="prereq_drill",
                prerequisite_modules=[],
                next_strategy=None,
                what_they_got_right=result.get("what_they_got_right", ""),
                concept_index=state.get("concept_index", 0),
                total_concepts=state.get("total_concepts", 1),
                concept_complete=False,
                prereq_active=True,
                prereq_concept=prereq_concept,
            )

    # ── Normal flow (not in prereq drill) ────────────────────────────────────

    # Determine next action
    if verdict == "MASTERED":
        next_action = "advance"
        new_attempt = attempt_number
    elif verdict == "INVALID_INPUT":
        next_action = "explain_back"
        new_attempt = attempt_number
    elif attempt_number >= MAX_ATTEMPTS:
        next_action = "flag_review"
        new_attempt = attempt_number + 1
    else:
        next_action = "reteach"
        new_attempt = attempt_number + 1

    should_advance = verdict == "MASTERED"
    should_flag    = next_action == "flag_review"

    # Track which strategy was just used
    current_strategy = state.get("teaching_strategy", "direct")
    strategies_used  = list(state.get("strategies_used", []))
    if current_strategy not in strategies_used:
        strategies_used.append(current_strategy)
    state["strategies_used"] = strategies_used

    # Track consecutive fails on this concept
    if verdict in ("PARTIAL", "NOT_YET"):
        consecutive_fails = state.get("consecutive_fails", 0) + 1
    else:
        consecutive_fails = 0
    state["consecutive_fails"] = consecutive_fails

    # Update core session state
    state["mastery_probability"] = mastery
    state["mastery_score"]       = mastery
    state["attempt_number"]      = new_attempt
    state["last_verdict"]        = verdict
    state["pain_point"]          = result.get("pain_point", "")
    if verdict not in ("MASTERED", "INVALID_INPUT"):
        pain_points = list(state.get("pain_points", []))
        if result.get("pain_point"):
            pain_points.append(result["pain_point"])
        state["pain_points"] = pain_points

    # ── Inline prereq drill trigger ───────────────────────────────────────────
    # Triggered when student fails the SAME concept twice in a row and the
    # validator identified a specific gap. Drills the foundational concept
    # transparently inside the conversation before resuming the main concept.
    if (
        consecutive_fails >= 2
        and verdict in ("PARTIAL", "NOT_YET")
        and result.get("pain_point")
        and not prereq_active
    ):
        from agents.teaching_agent import generate_prereq_drill
        module_obj      = state.get("module", {})
        concepts        = module_obj.get("concepts", [])
        concept_idx     = state.get("concept_index", 0)
        current_concept_title = (
            concepts[concept_idx].get("title", module_obj.get("title", ""))
            if concepts and concept_idx < len(concepts)
            else module_obj.get("title", "this concept")
        )

        print(f"[PREREQ_DRILL] Triggering drill after {consecutive_fails} fails on '{current_concept_title}'")
        print(f"[PREREQ_DRILL] Pain point: {result.get('pain_point', '')}")

        try:
            gap_name, micro_lesson = await generate_prereq_drill(
                pain_point=result.get("pain_point", ""),
                concept_title=current_concept_title,
                source_chunks=state.get("source_chunks", []),
                module_title=module_obj.get("title", ""),
            )
            print(f"[PREREQ_DRILL] Drilling: '{gap_name}'")

            # Persist this prerequisite gap to the student's learning plan
            try:
                _drill_student_id = state.get("student_id", "")
                existing_drill_prereq = await supabase_query(
                    "student_prerequisite_recommendations",
                    params={
                        "student_id": f"eq.{_drill_student_id}",
                        "linked_module_id": f"eq.{module_id}",
                        "topic": f"eq.{gap_name}",
                        "select": "id",
                    }
                )
                if not existing_drill_prereq:
                    await supabase_query(
                        "student_prerequisite_recommendations",
                        method="POST",
                        json={
                            "id": str(uuid.uuid4()),
                            "student_id": _drill_student_id,
                            "linked_module_id": module_id,
                            "topic": gap_name,
                            "reason": f"Blocking understanding of '{current_concept_title}'",
                            "brief_explanation": micro_lesson[:300] if micro_lesson else "",
                            "status": "pending",
                            "is_in_course": False,
                        },
                    )
            except Exception as e:
                print(f"[PREREQ_DRILL] Failed to save prereq to DB: {e}")

            state["prereq_active"]            = True
            state["prereq_concept"]           = gap_name
            state["prereq_explanation"]       = micro_lesson
            state["prereq_return_attempt"]    = new_attempt
            state["prereq_return_explanation"]= state.get("current_explanation", "")
            state["current_explanation"]      = micro_lesson
            state["consecutive_fails"]        = 0
            set_session(session_id, state)

            return ExplainResponse(
                session_id=session_id,
                attempt_number=new_attempt,
                verdict=verdict,
                pain_point=result.get("pain_point", ""),
                feedback_to_student=(
                    f"Before we continue, let's solidify one foundational piece: {gap_name}. "
                    f"Once we nail this, the main concept will click."
                ),
                concepts_missed=result.get("concepts_missed", []),
                scores=scores,
                mastery_probability=mastery,
                mastery_score=mastery,
                advance=False,
                next_action="prereq_drill",
                prerequisite_modules=[],
                next_strategy=None,
                what_they_got_right=result.get("what_they_got_right", ""),
                concept_index=concept_idx,
                total_concepts=state.get("total_concepts", 1),
                concept_complete=False,
                prereq_active=True,
                prereq_concept=gap_name,
            )
        except Exception as e:
            print(f"[PREREQ_DRILL] Generation failed: {e} — continuing normal reteach")

    # ── Normal reteach: pre-generate next explanation ─────────────────────────
    if next_action == "reteach":
        from agents.teaching_agent import select_adaptive_strategy as _sel
        next_strat = _sel(
            attempt_number=new_attempt,
            strategies_used=strategies_used,
            explicit_confusion=False,
            pain_points=state.get("pain_points", []),
        )
        state["teaching_strategy"] = next_strat
        try:
            next_explanation = await teach_concept(
                module=state.get("module", {}),
                student_history=state.get("student_history", []) + [{
                    "attempt_number": attempt_number,
                    "student_explanation": body.explanation,
                    "verdict": verdict,
                    "pain_point": result.get("pain_point", ""),
                }],
                source_chunks=state.get("source_chunks", []),
                strategy=next_strat,
                pain_point=result.get("pain_point", ""),
                attempt_number=new_attempt,
                concept_index=state.get("concept_index", 0),
                strategies_used=strategies_used,
                explicit_confusion=False,
                pain_points=state.get("pain_points", []),
            )
            state["current_explanation"] = next_explanation
        except Exception:
            state["current_explanation"] = ""

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
            from api.cf_client import complete_json as cf_json
            module_obj = state.get("module", {})
            concepts_missed = result.get("concepts_missed", [])
            pain_points_summary = "; ".join(state.get("pain_points", [])[-3:])
            topics_to_check = concepts_missed if concepts_missed else ([pain_points_summary] if pain_points_summary else [])
            if topics_to_check:
                pr_data = await cf_json(
                    messages=[{"role": "user", "content": f"""The student is struggling with: {module_obj.get('title', '')}
They are missing: {topics_to_check}

Suggest 2-3 prerequisite topics they need to understand BEFORE this module. These are foundational gaps, not part of this module's content. Return JSON:
{{"recommendations": [{{"topic": "...", "reason": "one sentence why this foundational topic is blocking their understanding", "brief_explanation": "2-3 sentences explaining this topic simply"}}]}}"""}],
                    model_key="course",
                    temperature=0.3,
                    max_tokens=400,
                )
                prereq_recs = pr_data.get("recommendations", [])
                state["prerequisite_modules"] = prereq_recs
                set_session(session_id, state)

                # Persist prerequisites to DB as separate learning plan items (not course modules)
                _student_id = state.get("student_id", "")
                _blocking_module_id = module_id
                for rec in prereq_recs:
                    topic = rec.get("topic", "").strip()
                    if not topic:
                        continue
                    try:
                        # Check if this prereq was already recommended to avoid duplicates
                        existing_prereq = await supabase_query(
                            "student_prerequisite_recommendations",
                            params={
                                "student_id": f"eq.{_student_id}",
                                "linked_module_id": f"eq.{_blocking_module_id}",
                                "topic": f"eq.{topic}",
                                "select": "id",
                            }
                        )
                        if not existing_prereq:
                            await supabase_query(
                                "student_prerequisite_recommendations",
                                method="POST",
                                json={
                                    "id": str(uuid.uuid4()),
                                    "student_id": _student_id,
                                    "linked_module_id": _blocking_module_id,
                                    "topic": topic,
                                    "reason": rec.get("reason", ""),
                                    "brief_explanation": rec.get("brief_explanation", ""),
                                    "status": "pending",
                                    "is_in_course": False,
                                },
                            )
                    except Exception as e:
                        print(f"[PREREQ_SAVE] Failed to save prereq '{topic}': {e}")
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
        prereq_active=state.get("prereq_active", False),
        prereq_concept=state.get("prereq_concept", ""),
    )


@router.post("/{session_id}/submodule")
async def generate_submodule_for_concept(session_id: str) -> dict:
    """
    Generate sub-concepts for the current stuck concept.

    Called when a student is struggling and wants to go deeper before
    retrying the original concept. Returns 3-4 ordered sub-concepts
    that the frontend can insert as a temporary sub-teaching sequence.
    """
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

    from agents.course_generator import generate_submodule

    module = state.get("module", {})
    concepts = module.get("concepts", [])
    concept_index = state.get("concept_index", 0)

    current_concept = (
        concepts[concept_index]
        if concepts and concept_index < len(concepts)
        else {"title": module.get("title", ""), "learning_objective": "", "key_points": []}
    )

    pain_point = state.get("pain_point", "")
    # Synthesize a richer pain_point from accumulated pain_points
    accumulated = state.get("pain_points", [])
    if accumulated:
        pain_point = "; ".join(dict.fromkeys(p for p in accumulated if p)[-3:])

    sub_concepts = await generate_submodule(
        concept=current_concept,
        source_chunks=state.get("source_chunks", []),
        pain_point=pain_point,
        module_title=module.get("title", ""),
    )

    return {
        "session_id": session_id,
        "parent_concept": current_concept,
        "sub_concepts": sub_concepts,
        "count": len(sub_concepts),
    }


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
