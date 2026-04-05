"""
api/routes/dashboard.py
Professor dashboard: stats, heatmap with pain points, interventions, LMS export, assignment generation.
"""
from __future__ import annotations
import os, json, uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from api.db import supabase_query

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/{course_id}/stats")
async def get_stats(course_id: str):
    enrollments = await supabase_query("enrollments", params={"course_id": f"eq.{course_id}", "select": "id,student_id"})
    modules = await supabase_query("modules", params={"course_id": f"eq.{course_id}", "select": "id"})
    module_ids = [m["id"] for m in modules]
    
    sessions = []
    if module_ids:
        id_list = "(" + ",".join(module_ids) + ")"
        sessions = await supabase_query("sessions", params={"module_id": f"in.{id_list}", "select": "mastery_score,completed_at,student_id"})
    
    enrollment_count = len(enrollments)
    avg_mastery = round(sum(s.get("mastery_score", 0) for s in sessions) / len(sessions), 3) if sessions else 0.0
    completed = sum(1 for s in sessions if s.get("completed_at"))
    completion_rate = round(completed / len(sessions), 3) if sessions else 0.0
    
    return {
        "enrollment_count": enrollment_count,
        "avg_mastery": avg_mastery,
        "completion_rate": completion_rate,
        "module_count": len(modules),
        "total_sessions": len(sessions),
    }


@router.get("/{course_id}/heatmap")
async def get_heatmap(course_id: str):
    modules = await supabase_query("modules", params={"course_id": f"eq.{course_id}", "select": "id,title,order_index"})
    modules_sorted = sorted(modules, key=lambda m: m.get("order_index", 0))
    
    enrollments = await supabase_query("enrollments", params={"course_id": f"eq.{course_id}", "select": "student_id"})
    student_ids = list(set(e["student_id"] for e in enrollments))
    
    students = []
    for sid in student_ids:
        s = await supabase_query("students", params={"id": f"eq.{sid}", "select": "id,name,email"})
        if s:
            students.append(s[0])
    
    module_ids = [m["id"] for m in modules_sorted]
    all_sessions = []
    if module_ids:
        id_list = "(" + ",".join(module_ids) + ")"
        all_sessions = await supabase_query("sessions", params={"module_id": f"in.{id_list}", "select": "id,student_id,module_id,mastery_score,completed_at"})
    
    # Get pain points from kc_attempts
    session_ids = [s["id"] for s in all_sessions]
    pain_point_map = {}  # (student_id, module_id) -> pain_point
    if session_ids:
        id_list = "(" + ",".join(session_ids[:200]) + ")"
        attempts = await supabase_query("kc_attempts", params={
            "session_id": f"in.{id_list}",
            "select": "session_id,validator_scores,created_at",
        })
        # Sort by created_at desc to get latest
        attempts_sorted = sorted(attempts, key=lambda a: a.get("created_at", ""), reverse=True)
        session_to_student_module = {s["id"]: (s["student_id"], s["module_id"]) for s in all_sessions}
        
        for attempt in attempts_sorted:
            scores = attempt.get("validator_scores", {}) or {}
            verdict = scores.get("verdict", "")
            pain = scores.get("pain_point", "")
            sid = attempt.get("session_id", "")
            key = session_to_student_module.get(sid)
            if key and key not in pain_point_map and verdict != "MASTERED" and pain:
                pain_point_map[key] = pain
    
    cells = []
    for student in students:
        for module in modules_sorted:
            mod_sessions = [s for s in all_sessions if s["student_id"] == student["id"] and s["module_id"] == module["id"]]
            attempts_count = len(mod_sessions)
            best_mastery = max((s.get("mastery_score", 0) for s in mod_sessions), default=0.0)
            
            if attempts_count == 0:
                status = "not_started"
            elif best_mastery >= 0.75:
                status = "mastered"
            elif attempts_count >= 5 and best_mastery < 0.4:
                status = "needs_review"
            else:
                status = "in_progress"
            
            pain_point = pain_point_map.get((student["id"], module["id"]), "")
            
            cells.append({
                "student_id": student["id"],
                "module_id": module["id"],
                "mastery_score": round(best_mastery, 3),
                "status": status,
                "attempts": attempts_count,
                "latest_pain_point": pain_point,
            })
    
    return {
        "modules": [{"id": m["id"], "title": m["title"], "module_order": m.get("order_index", 0)} for m in modules_sorted],
        "students": students,
        "cells": cells,
    }


@router.get("/{course_id}/interventions")
async def get_interventions(course_id: str):
    modules = await supabase_query("modules", params={"course_id": f"eq.{course_id}", "select": "id,title"})
    module_map = {m["id"]: m["title"] for m in modules}
    module_ids = list(module_map.keys())
    
    enrollments = await supabase_query("enrollments", params={"course_id": f"eq.{course_id}", "select": "student_id"})
    student_ids = list(set(e["student_id"] for e in enrollments))
    
    interventions = []
    for sid in student_ids:
        student = await supabase_query("students", params={"id": f"eq.{sid}", "select": "id,name,email"})
        if not student:
            continue
        student = student[0]
        
        if not module_ids:
            continue
        id_list = "(" + ",".join(module_ids) + ")"
        sessions = await supabase_query("sessions", params={"student_id": f"eq.{sid}", "module_id": f"in.{id_list}", "select": "id,module_id,mastery_score,completed_at"})
        
        if not sessions:
            continue
        
        avg_mastery = sum(s.get("mastery_score", 0) for s in sessions) / len(sessions)
        if avg_mastery >= 0.5:
            continue  # Not at risk
        
        # Find stuck modules
        stuck = {}
        for s in sessions:
            mid = s["module_id"]
            if mid not in stuck:
                stuck[mid] = {"attempts": 0, "best_mastery": 0, "session_ids": []}
            stuck[mid]["attempts"] += 1
            stuck[mid]["best_mastery"] = max(stuck[mid]["best_mastery"], s.get("mastery_score", 0))
            stuck[mid]["session_ids"].append(s["id"])
        
        stuck_modules = []
        for mid, data in stuck.items():
            if data["best_mastery"] < 0.5 and data["attempts"] >= 2:
                # Get pain points
                pain_points = []
                if data["session_ids"]:
                    sess_id_list = "(" + ",".join(data["session_ids"]) + ")"
                    attempts_data = await supabase_query("kc_attempts", params={"session_id": f"in.{sess_id_list}", "select": "validator_scores"})
                    for a in attempts_data:
                        scores = a.get("validator_scores", {}) or {}
                        pain = scores.get("pain_point", "")
                        if pain and pain not in pain_points:
                            pain_points.append(pain)
                
                # Get prereq recommendations
                prereqs = await supabase_query("student_prerequisite_recommendations", params={"student_id": f"eq.{sid}", "module_id": f"eq.{mid}", "select": "topic"})
                prereq_topics = [p["topic"] for p in prereqs]
                
                stuck_modules.append({
                    "module_id": mid,
                    "module_title": module_map.get(mid, "Unknown"),
                    "attempts": data["attempts"],
                    "pain_points": pain_points[:3],
                    "recommended_prerequisites": prereq_topics,
                })
        
        if stuck_modules:
            interventions.append({
                "student_id": sid,
                "student_name": student.get("name", "Unknown"),
                "avg_mastery": round(avg_mastery, 3),
                "severity": "high" if avg_mastery < 0.3 else "medium",
                "stuck_modules": stuck_modules,
            })
    
    return interventions


@router.get("/{course_id}/export")
async def export_lms(course_id: str):
    course = await supabase_query("courses", params={"id": f"eq.{course_id}", "select": "id,title,description"})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    modules = await supabase_query("modules", params={"course_id": f"eq.{course_id}", "select": "id,title,description,learning_objectives,order_index,estimated_minutes"})
    modules_sorted = sorted(modules, key=lambda m: m.get("order_index", 0))
    
    export = {
        "course": course[0],
        "modules": modules_sorted,
        "scorm_version": "2004",
        "export_format": "json",
    }
    return JSONResponse(content=export)
