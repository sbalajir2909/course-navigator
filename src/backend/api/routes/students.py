"""
api/routes/students.py
Student progress, prerequisites, and profile endpoints.
"""
from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException
from api.db import supabase_query

router = APIRouter(prefix="/api/students", tags=["students"])

@router.get("/{student_id}/progress")
async def get_student_progress(student_id: str):
    """Full student progress: mastery by module, over time, prerequisites, stats."""
    # Get all sessions for this student
    sessions = await supabase_query("sessions", params={
        "student_id": f"eq.{student_id}",
        "select": "id,module_id,mastery_score,completed_at,started_at"
    })
    
    # Get module details
    module_ids = list(set(s["module_id"] for s in sessions))
    modules_map = {}
    for mid in module_ids:
        mods = await supabase_query("modules", params={"id": f"eq.{mid}", "select": "id,title,order_index"})
        if mods:
            modules_map[mid] = mods[0]
    
    # Build mastery by module
    mastery_by_module = []
    for mid in module_ids:
        mod_sessions = [s for s in sessions if s["module_id"] == mid]
        best_mastery = max((s.get("mastery_score", 0) for s in mod_sessions), default=0)
        attempts = len(mod_sessions)
        completed = any(s.get("completed_at") for s in mod_sessions)
        status = "mastered" if best_mastery >= 0.75 else ("in_progress" if attempts > 0 else "not_started")
        mastery_by_module.append({
            "module_id": mid,
            "title": modules_map.get(mid, {}).get("title", "Unknown"),
            "mastery_score": round(best_mastery, 3),
            "attempts": attempts,
            "status": status,
            "completed": completed,
        })
    
    mastery_by_module.sort(key=lambda x: modules_map.get(x["module_id"], {}).get("order_index", 0))
    
    # Mastery over time (one point per session)
    mastery_over_time = []
    for s in sorted(sessions, key=lambda x: x.get("started_at", "")):
        if s.get("started_at") and s.get("mastery_score") is not None:
            mastery_over_time.append({
                "date": s["started_at"],
                "overall_mastery": round(s.get("mastery_score", 0) * 100, 1),
                "module_id": s["module_id"],
            })
    
    # Get prerequisites
    prereqs = await supabase_query("student_prerequisite_recommendations", params={
        "student_id": f"eq.{student_id}",
        "select": "id,topic,reason,brief_explanation,status,is_in_course,linked_module_id"
    })
    
    # Stats
    mastered = sum(1 for m in mastery_by_module if m["status"] == "mastered")
    total = len(mastery_by_module)
    avg_mastery = sum(m["mastery_score"] for m in mastery_by_module) / total if total > 0 else 0
    
    return {
        "student_id": student_id,
        "mastery_by_module": mastery_by_module,
        "mastery_over_time": mastery_over_time,
        "prerequisites": prereqs,
        "stats": {
            "modules_mastered": mastered,
            "total_modules": total,
            "avg_mastery": round(avg_mastery, 3),
            "streak": 0,  # TODO: implement streak logic
        }
    }

@router.get("/{student_id}/prerequisites")
async def get_prerequisites(student_id: str):
    return await supabase_query("student_prerequisite_recommendations", params={
        "student_id": f"eq.{student_id}",
        "select": "*"
    })

@router.post("/{student_id}/prerequisites/{prereq_id}/complete")
async def complete_prerequisite(student_id: str, prereq_id: str):
    await supabase_query(
        f"student_prerequisite_recommendations?id=eq.{prereq_id}&student_id=eq.{student_id}",
        method="PATCH",
        json={"status": "completed"}
    )
    return {"status": "completed"}
