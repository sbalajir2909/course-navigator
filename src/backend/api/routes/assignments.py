"""
api/routes/assignments.py
Assignment generation, approval, student submission, and auto-grading.
"""
from __future__ import annotations
import os, json, uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.db import supabase_query
from groq import Groq

router = APIRouter(prefix="/api/assignments", tags=["assignments"])


class SubmitRequest(BaseModel):
    student_id: str
    submission_text: str

class ReleaseRequest(BaseModel):
    professor_feedback: str = ""
    override_grade: float | None = None


async def _auto_grade(submission_text: str, rubric: list[dict]) -> dict:
    """Auto-grade a submission against each rubric criterion using Groq."""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    results = []
    total = 0.0
    
    for criterion in rubric:
        prompt = f"""Grade this student submission against this criterion.

CRITERION: {criterion.get('criterion', '')}
MAX POINTS: {criterion.get('max_points', 10)}
WHAT FULL MARKS LOOKS LIKE: {criterion.get('description', '')}

STUDENT SUBMISSION:
"{submission_text}"

Return JSON:
{{"score": 0-{criterion.get('max_points', 10)}, "feedback": "One sentence explaining the score"}}"""
        
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=100,
            )
            result = json.loads(response.choices[0].message.content)
            score = min(float(result.get("score", 0)), criterion.get("max_points", 10))
            results.append({
                "criterion": criterion.get("criterion"),
                "score": score,
                "max_points": criterion.get("max_points", 10),
                "feedback": result.get("feedback", ""),
            })
            total += score
        except Exception:
            results.append({"criterion": criterion.get("criterion"), "score": 0, "max_points": criterion.get("max_points", 10), "feedback": "Error grading"})
    
    return {"criteria_results": results, "total": round(total, 1)}


@router.post("/generate/{course_id}")
async def generate_assignments(course_id: str):
    """Generate AI assignments based on class performance data."""
    course = await supabase_query("courses", params={"id": f"eq.{course_id}", "select": "id,title"})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    modules = await supabase_query("modules", params={"course_id": f"eq.{course_id}", "select": "id,title,order_index"})
    module_ids = [m["id"] for m in modules]
    
    # Aggregate performance data
    sessions = []
    if module_ids:
        id_list = "(" + ",".join(module_ids) + ")"
        sessions = await supabase_query("sessions", params={"module_id": f"in.{id_list}", "select": "id,module_id,mastery_score,student_id"})
    
    # Mastery by module
    module_mastery = {}
    for s in sessions:
        mid = s["module_id"]
        if mid not in module_mastery:
            module_mastery[mid] = []
        module_mastery[mid].append(s.get("mastery_score", 0))
    
    module_title_map = {m["id"]: m["title"] for m in modules}
    struggling_modules = [
        {"id": mid, "title": module_title_map.get(mid, ""), "avg_mastery": round(sum(scores)/len(scores), 2)}
        for mid, scores in module_mastery.items()
        if sum(scores)/len(scores) < 0.5
    ]
    
    # Student distribution
    student_masteries = {}
    for s in sessions:
        sid = s["student_id"]
        if sid not in student_masteries:
            student_masteries[sid] = []
        student_masteries[sid].append(s.get("mastery_score", 0))
    
    avg_per_student = [sum(v)/len(v) for v in student_masteries.values()]
    struggling_count = sum(1 for m in avg_per_student if m < 0.4)
    on_track_count = sum(1 for m in avg_per_student if 0.4 <= m <= 0.75)
    advanced_count = sum(1 for m in avg_per_student if m > 0.75)
    
    # Get top pain points
    session_ids = [s["id"] for s in sessions[:50]] if sessions else []
    top_pain_points = []
    if session_ids:
        id_list = "(" + ",".join(session_ids) + ")"
        attempts = await supabase_query("kc_attempts", params={"session_id": f"in.{id_list}", "select": "validator_scores"})
        pain_counts = {}
        for a in attempts:
            scores = a.get("validator_scores", {}) or {}
            pain = scores.get("pain_point", "")
            if pain:
                pain_counts[pain] = pain_counts.get(pain, 0) + 1
        top_pain_points = sorted(pain_counts.keys(), key=lambda p: pain_counts[p], reverse=True)[:5]
    
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    prompt = f"""You are designing assignments for a class learning: {course[0]['title']}

Class performance:
- Struggling modules (avg mastery < 50%): {[m['title'] for m in struggling_modules]}
- Common student pain points: {top_pain_points}
- Distribution: {struggling_count} struggling, {on_track_count} on track, {advanced_count} advanced

Generate 3 assignments. Requirements:
1. At least one targets the weakest module
2. Include one "foundational" (struggling students), one "standard" (all), one "advanced"
3. Each must have a clear rubric with specific gradeable criteria
4. Instructions must be self-contained — student needs no extra context

Return ONLY valid JSON:
{{
  "assignments": [
    {{
      "title": "...",
      "description": "...",
      "target_module_ids": [],
      "difficulty": "foundational",
      "target_students": "struggling",
      "instructions": "Full instructions here",
      "rubric": [{{"criterion": "...", "max_points": 10, "description": "What full marks looks like"}}],
      "estimated_minutes": 30
    }}
  ]
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
            max_tokens=1000,
        )
        data = json.loads(response.choices[0].message.content)
        assignments_data = data.get("assignments", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assignment generation failed: {str(e)}")
    
    # Store in DB
    created = []
    for a in assignments_data:
        aid = str(uuid.uuid4())
        await supabase_query("assignments", method="POST", json={
            "id": aid, "course_id": course_id,
            "title": a.get("title", ""), "description": a.get("description", ""),
            "instructions": a.get("instructions", ""),
            "rubric": a.get("rubric", []),
            "difficulty": a.get("difficulty", "standard"),
            "target_students": a.get("target_students", "all"),
            "target_module_ids": a.get("target_module_ids", []),
            "estimated_minutes": a.get("estimated_minutes", 30),
            "status": "pending_approval",
        })
        created.append({"id": aid, **a})
    
    return {"assignments": created, "count": len(created)}


@router.get("/course/{course_id}")
async def get_course_assignments(course_id: str):
    return await supabase_query("assignments", params={"course_id": f"eq.{course_id}", "select": "*"})


@router.get("/student/{student_id}")
async def get_student_assignments(student_id: str):
    # Get courses this student is enrolled in
    enrollments = await supabase_query("enrollments", params={"student_id": f"eq.{student_id}", "select": "course_id"})
    course_ids = list(set(e["course_id"] for e in enrollments))
    if not course_ids:
        return []
    id_list = "(" + ",".join(course_ids) + ")"
    return await supabase_query("assignments", params={"course_id": f"in.{id_list}", "status": "eq.approved", "select": "*"})


@router.post("/{assignment_id}/approve")
async def approve_assignment(assignment_id: str):
    await supabase_query(f"assignments?id=eq.{assignment_id}", method="PATCH", json={"status": "approved"})
    return {"status": "approved"}


@router.post("/{assignment_id}/reject")
async def reject_assignment(assignment_id: str):
    await supabase_query(f"assignments?id=eq.{assignment_id}", method="PATCH", json={"status": "rejected"})
    return {"status": "rejected"}


@router.post("/{assignment_id}/submit")
async def submit_assignment(assignment_id: str, body: SubmitRequest):
    assignment = await supabase_query("assignments", params={"id": f"eq.{assignment_id}", "select": "*"})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    rubric = assignment[0].get("rubric", [])
    grade_result = await _auto_grade(body.submission_text, rubric if isinstance(rubric, list) else [])
    
    submission_id = str(uuid.uuid4())
    await supabase_query("assignment_submissions", method="POST", json={
        "id": submission_id,
        "assignment_id": assignment_id,
        "student_id": body.student_id,
        "submission_text": body.submission_text,
        "auto_grade_result": grade_result,
        "auto_grade_total": grade_result.get("total", 0),
        "grade_released": False,
    })
    
    return {"submission_id": submission_id, "auto_grade_result": grade_result}


@router.post("/submissions/{submission_id}/release")
async def release_grade(submission_id: str, body: ReleaseRequest):
    update = {"grade_released": True, "professor_feedback": body.professor_feedback}
    if body.override_grade is not None:
        update["professor_override_grade"] = body.override_grade
    await supabase_query(f"assignment_submissions?id=eq.{submission_id}", method="PATCH", json=update)
    return {"status": "released"}
