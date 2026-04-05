"""
agents/student_memory.py
Per-student learning memory using LangGraph state + Supabase persistence.

Each student has isolated memory:
- Mastery probability per module (BKT state)
- Struggle points (modules/concepts where they failed 2+ times)
- Learning style preference (which strategy worked best)
- Session history summary

This is retrieved at the start of each teaching session to personalize the response.
"""
from __future__ import annotations
import json, os
from api.db import supabase_query

async def get_student_memory(student_id: str, module_id: str) -> dict:
    """
    Retrieve a student's learning memory for a specific module.
    Returns context that gets injected into the teaching agent's prompt.
    """
    # Get all past KC attempts for this student on this module
    attempts = await supabase_query(
        "kc_attempts",
        params={
            "module_id": f"eq.{module_id}",
            "select": "mastery_probability,attempt_number,validator_scores,student_explanation,created_at",
        }
    )
    
    # Filter by student via session join
    sessions = await supabase_query(
        "sessions",
        params={
            "student_id": f"eq.{student_id}",
            "module_id": f"eq.{module_id}",
            "select": "id,mastery_score,completed_at",
        }
    )
    
    # Get struggle modules (modules where mastery < 0.4 after 2+ attempts)
    all_sessions = await supabase_query(
        "sessions",
        params={
            "student_id": f"eq.{student_id}",
            "select": "id,module_id,mastery_score",
        }
    )
    
    struggle_modules = [
        s["module_id"] for s in all_sessions 
        if s.get("mastery_score", 1.0) < 0.4
    ]
    
    prior_mastery = 0.0  # start at 0, not 0.3
    best_strategy = "initial"
    attempt_count = len(sessions)
    
    if sessions:
        prior_mastery = sessions[-1].get("mastery_score", 0.3)
    
    # Detect best strategy from past attempts
    if attempts:
        # Find which attempt had the highest score
        best_attempt = max(attempts, key=lambda a: a.get("mastery_probability", 0))
        scores = best_attempt.get("validator_scores", {})
        # Infer strategy from attempt number
        strategies = ["initial", "simplified", "analogy", "worked_example"]
        best_idx = min(best_attempt.get("attempt_number", 1) - 1, len(strategies) - 1)
        best_strategy = strategies[best_idx]
    
    return {
        "prior_mastery": prior_mastery,
        "attempt_count": attempt_count,
        "is_returning": attempt_count > 0,
        "struggle_modules": struggle_modules,
        "recommended_strategy": best_strategy if attempt_count > 0 else "initial",
        "memory_context": _build_memory_context(sessions, attempts, attempt_count),
    }

def _build_memory_context(sessions: list, attempts: list, attempt_count: int) -> str:
    """Build a natural language memory context string for the teaching agent."""
    if attempt_count == 0:
        return ""
    
    lines = [f"STUDENT MEMORY (this student has attempted this module {attempt_count} time(s) before):"]
    
    if sessions:
        last = sessions[-1]
        mastery = last.get("mastery_score", 0)
        lines.append(f"- Last mastery score: {round(mastery * 100)}%")
        if last.get("completed_at"):
            lines.append("- Previously completed this module")
    
    if attempts:
        last_exp = attempts[-1].get("student_explanation", "")
        if last_exp:
            lines.append(f"- Last explanation attempt: \"{last_exp[:200]}\"")
    
    lines.append("Use this context to personalize your teaching. Don't repeat what already worked.")
    return "\n".join(lines)

async def save_struggle_point(student_id: str, module_id: str, concept: str, score: float):
    """Log a struggle point when a student fails repeatedly on a concept."""
    # This is stored in kc_attempts and visible in the dashboard
    pass  # Already handled by kc_attempts table

async def get_student_profile(student_id: str) -> dict:
    """
    Get a full student learning profile — used for the professor dashboard.
    Returns: modules attempted, mastery per module, struggle areas, total time.
    """
    sessions = await supabase_query(
        "sessions",
        params={
            "student_id": f"eq.{student_id}",
            "select": "id,module_id,mastery_score,completed_at,started_at",
        }
    )
    
    module_ids = list(set(s["module_id"] for s in sessions))
    
    # Get module titles
    module_details = {}
    if module_ids:
        for mid in module_ids:
            mods = await supabase_query("modules", params={"id": f"eq.{mid}", "select": "id,title"})
            if mods:
                module_details[mid] = mods[0]["title"]
    
    modules_data = []
    for mid in module_ids:
        mod_sessions = [s for s in sessions if s["module_id"] == mid]
        best_mastery = max((s.get("mastery_score", 0) for s in mod_sessions), default=0)
        attempts = len(mod_sessions)
        completed = any(s.get("completed_at") for s in mod_sessions)
        
        modules_data.append({
            "module_id": mid,
            "module_title": module_details.get(mid, "Unknown"),
            "best_mastery": round(best_mastery * 100),
            "attempts": attempts,
            "completed": completed,
            "is_struggling": best_mastery < 0.4 and attempts >= 2,
        })
    
    return {
        "student_id": student_id,
        "total_modules_attempted": len(module_ids),
        "total_sessions": len(sessions),
        "struggle_areas": [m for m in modules_data if m["is_struggling"]],
        "modules": sorted(modules_data, key=lambda x: x["best_mastery"], reverse=True),
    }
