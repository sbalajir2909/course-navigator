"""
api/routes/dashboard.py
Professor analytics dashboard: stats, heatmaps, interventions, and LMS export.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.db import supabase_query

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ─────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────

class CourseStats(BaseModel):
    course_id: str
    title: str
    enrollment_count: int
    avg_mastery: float
    completion_rate: float
    module_count: int
    assessment_count: int


class HeatmapCell(BaseModel):
    student_id: str
    student_name: str
    module_id: str
    module_title: str
    mastery_score: float
    completed: bool


class HeatmapResponse(BaseModel):
    course_id: str
    modules: list[dict[str, str]]   # [{id, title}]
    students: list[dict[str, str]]  # [{id, name}]
    cells: list[HeatmapCell]


class InterventionStudent(BaseModel):
    student_id: str
    student_name: str
    student_email: str
    avg_mastery: float
    low_mastery_modules: list[dict[str, Any]]  # [{module_id, module_title, mastery}]


# ─────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────

async def _verify_course(course_id: str) -> dict[str, Any]:
    """Fetch course or raise 404."""
    courses = await supabase_query(
        "courses",
        params={"id": f"eq.{course_id}", "select": "id,title"},
    )
    if not courses:
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found.")
    return courses[0]


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@router.get("/{course_id}/stats", response_model=CourseStats)
async def get_course_stats(course_id: str) -> CourseStats:
    """
    Return overall course analytics:
      - Enrollment count
      - Average mastery across all completed sessions
      - Completion rate (% of enrolled students with ≥1 completed session)
      - Module and assessment counts
    """
    course = await _verify_course(course_id)

    # Enrollment count
    enrollments = await supabase_query(
        "enrollments",
        params={"course_id": f"eq.{course_id}", "select": "id,student_id"},
    )
    enrollment_count = len(enrollments)

    # Module count
    modules = await supabase_query(
        "modules",
        params={"course_id": f"eq.{course_id}", "select": "id"},
    )
    module_count = len(modules)

    # Assessment count
    assessment_count = 0
    if modules:
        module_ids = [m["id"] for m in modules]
        id_list = "(" + ",".join(module_ids) + ")"
        assessments = await supabase_query(
            "assessments",
            params={"module_id": f"in.{id_list}", "select": "id"},
        )
        assessment_count = len(assessments)

    # Session stats: avg mastery & completion rate
    avg_mastery = 0.0
    completion_rate = 0.0

    if enrollment_count > 0 and modules:
        # Get all sessions for this course's modules
        id_list = "(" + ",".join([m["id"] for m in modules]) + ")"
        sessions = await supabase_query(
            "sessions",
            params={
                "module_id": f"in.{id_list}",
                "select": "student_id,mastery_score,completed_at",
            },
        )

        if sessions:
            all_mastery = [s["mastery_score"] for s in sessions if s.get("mastery_score") is not None]
            avg_mastery = sum(all_mastery) / len(all_mastery) if all_mastery else 0.0

            # Students with at least one completed session
            completed_student_ids = {
                s["student_id"] for s in sessions if s.get("completed_at")
            }
            enrolled_student_ids = {e["student_id"] for e in enrollments}
            completing_students = completed_student_ids & enrolled_student_ids
            completion_rate = len(completing_students) / enrollment_count

    return CourseStats(
        course_id=course_id,
        title=course["title"],
        enrollment_count=enrollment_count,
        avg_mastery=round(avg_mastery, 4),
        completion_rate=round(completion_rate, 4),
        module_count=module_count,
        assessment_count=assessment_count,
    )


@router.get("/{course_id}/heatmap", response_model=HeatmapResponse)
async def get_course_heatmap(course_id: str) -> HeatmapResponse:
    """
    Return a module × student mastery heatmap.

    Each cell represents the best mastery score a student achieved
    for a given module (highest mastery_score from all their sessions).
    """
    await _verify_course(course_id)

    # Fetch modules
    modules = await supabase_query(
        "modules",
        params={
            "course_id": f"eq.{course_id}",
            "select": "id,title",
            "order": "order_index.asc",
        },
    )
    if not modules:
        return HeatmapResponse(course_id=course_id, modules=[], students=[], cells=[])

    # Fetch enrolled students
    enrollments = await supabase_query(
        "enrollments",
        params={"course_id": f"eq.{course_id}", "select": "student_id"},
    )
    if not enrollments:
        return HeatmapResponse(
            course_id=course_id,
            modules=[{"id": m["id"], "title": m["title"]} for m in modules],
            students=[],
            cells=[],
        )

    student_ids = list({e["student_id"] for e in enrollments})
    id_list_students = "(" + ",".join(student_ids) + ")"

    # Fetch student details
    students_raw = await supabase_query(
        "students",
        params={
            "id": f"in.{id_list_students}",
            "select": "id,name",
        },
    )
    student_map = {s["id"]: s["name"] for s in students_raw}

    # Fetch all sessions for these modules
    module_ids = [m["id"] for m in modules]
    id_list_modules = "(" + ",".join(module_ids) + ")"
    sessions = await supabase_query(
        "sessions",
        params={
            "module_id": f"in.{id_list_modules}",
            "student_id": f"in.{id_list_students}",
            "select": "student_id,module_id,mastery_score,completed_at",
        },
    )

    # Build best-mastery map: (student_id, module_id) → max mastery_score
    best_mastery: dict[tuple[str, str], float] = {}
    completed_map: dict[tuple[str, str], bool] = {}
    for s in sessions:
        key = (s["student_id"], s["module_id"])
        current_best = best_mastery.get(key, 0.0)
        score = s.get("mastery_score") or 0.0
        if score > current_best:
            best_mastery[key] = score
        if s.get("completed_at"):
            completed_map[key] = True

    # Build cells
    cells: list[HeatmapCell] = []
    for student_id in student_ids:
        for module in modules:
            module_id = module["id"]
            key = (student_id, module_id)
            mastery = best_mastery.get(key, 0.0)
            completed = completed_map.get(key, False)
            cells.append(
                HeatmapCell(
                    student_id=student_id,
                    student_name=student_map.get(student_id, "Unknown"),
                    module_id=module_id,
                    module_title=module["title"],
                    mastery_score=round(mastery, 4),
                    completed=completed,
                )
            )

    return HeatmapResponse(
        course_id=course_id,
        modules=[{"id": m["id"], "title": m["title"]} for m in modules],
        students=[{"id": sid, "name": student_map.get(sid, "Unknown")} for sid in student_ids],
        cells=cells,
    )


@router.get("/{course_id}/interventions", response_model=list[InterventionStudent])
async def get_interventions(course_id: str) -> list[InterventionStudent]:
    """
    List students with average mastery below 0.4 — candidates for intervention.

    Returns student details + which specific modules are low-mastery.
    """
    await _verify_course(course_id)

    # Fetch enrolled students
    enrollments = await supabase_query(
        "enrollments",
        params={"course_id": f"eq.{course_id}", "select": "student_id"},
    )
    if not enrollments:
        return []

    student_ids = list({e["student_id"] for e in enrollments})

    # Fetch student details
    id_list_students = "(" + ",".join(student_ids) + ")"
    students_raw = await supabase_query(
        "students",
        params={
            "id": f"in.{id_list_students}",
            "select": "id,name,email",
        },
    )
    student_map = {s["id"]: s for s in students_raw}

    # Fetch modules
    modules = await supabase_query(
        "modules",
        params={"course_id": f"eq.{course_id}", "select": "id,title"},
    )
    if not modules:
        return []

    module_map = {m["id"]: m["title"] for m in modules}
    module_ids = list(module_map.keys())
    id_list_modules = "(" + ",".join(module_ids) + ")"

    # Fetch sessions
    sessions = await supabase_query(
        "sessions",
        params={
            "module_id": f"in.{id_list_modules}",
            "student_id": f"in.{id_list_students}",
            "select": "student_id,module_id,mastery_score",
        },
    )

    # Compute per-student, per-module best mastery
    student_module_mastery: dict[str, dict[str, float]] = {}
    for s in sessions:
        sid = s["student_id"]
        mid = s["module_id"]
        score = s.get("mastery_score") or 0.0
        student_module_mastery.setdefault(sid, {})
        current = student_module_mastery[sid].get(mid, 0.0)
        if score > current:
            student_module_mastery[sid][mid] = score

    INTERVENTION_THRESHOLD = 0.4
    result: list[InterventionStudent] = []

    for student_id in student_ids:
        module_scores = student_module_mastery.get(student_id, {})
        if not module_scores:
            # No activity yet — flag as needing intervention
            avg_mastery = 0.0
        else:
            avg_mastery = sum(module_scores.values()) / len(module_scores)

        if avg_mastery < INTERVENTION_THRESHOLD:
            low_mastery_mods = [
                {
                    "module_id": mid,
                    "module_title": module_map.get(mid, "Unknown"),
                    "mastery": round(score, 4),
                }
                for mid, score in module_scores.items()
                if score < INTERVENTION_THRESHOLD
            ]
            # Sort by mastery ascending
            low_mastery_mods.sort(key=lambda x: x["mastery"])

            student_info = student_map.get(student_id, {})
            result.append(
                InterventionStudent(
                    student_id=student_id,
                    student_name=student_info.get("name", "Unknown"),
                    student_email=student_info.get("email", ""),
                    avg_mastery=round(avg_mastery, 4),
                    low_mastery_modules=low_mastery_mods,
                )
            )

    # Sort by avg_mastery ascending (worst first)
    result.sort(key=lambda x: x.avg_mastery)
    return result


@router.get("/{course_id}/export")
async def export_course(course_id: str) -> JSONResponse:
    """
    Export the full course as an LMS-compatible JSON package.

    Includes: course metadata, modules, prerequisites, learning objectives,
    assessments, and aggregate student performance data.
    """
    course = await _verify_course(course_id)

    # Fetch modules
    modules = await supabase_query(
        "modules",
        params={
            "course_id": f"eq.{course_id}",
            "select": "id,title,description,learning_objectives,order_index,estimated_minutes,source_type,faithfulness_verdict",
            "order": "order_index.asc",
        },
    )

    module_ids = [m["id"] for m in modules]
    id_list = "(" + ",".join(module_ids) + ")" if module_ids else "()"

    # Prerequisites
    prereqs: list[dict[str, Any]] = []
    if module_ids:
        prereqs = await supabase_query(
            "prerequisites",
            params={
                "module_id": f"in.{id_list}",
                "select": "module_id,prerequisite_module_id",
            },
        )

    # Assessments
    assessments: list[dict[str, Any]] = []
    if module_ids:
        assessments = await supabase_query(
            "assessments",
            params={
                "module_id": f"in.{id_list}",
                "select": "id,module_id,question,question_type,options,correct_answer,difficulty_tier",
            },
        )

    # Enrollment count
    enrollments = await supabase_query(
        "enrollments",
        params={"course_id": f"eq.{course_id}", "select": "id"},
    )

    # Build assessment map
    assessments_by_module: dict[str, list[dict[str, Any]]] = {}
    for a in assessments:
        assessments_by_module.setdefault(a["module_id"], []).append(
            {
                "id": a["id"],
                "question": a["question"],
                "question_type": a["question_type"],
                "options": a.get("options"),
                "correct_answer": a["correct_answer"],
                "difficulty_tier": a["difficulty_tier"],
            }
        )

    # Build prereq map
    prereq_map: dict[str, list[str]] = {}
    for p in prereqs:
        prereq_map.setdefault(p["module_id"], []).append(p["prerequisite_module_id"])

    lms_export = {
        "schema_version": "1.0.0",
        "platform": "Assign B2B",
        "course": {
            "id": course["id"],
            "title": course["title"],
            "enrollment_count": len(enrollments),
        },
        "modules": [
            {
                "id": m["id"],
                "title": m["title"],
                "description": m.get("description", ""),
                "learning_objectives": m.get("learning_objectives") or [],
                "order_index": m.get("order_index", 0),
                "estimated_minutes": m.get("estimated_minutes", 30),
                "source_type": m.get("source_type", "material"),
                "faithfulness_verdict": m.get("faithfulness_verdict"),
                "prerequisite_module_ids": prereq_map.get(m["id"], []),
                "assessments": assessments_by_module.get(m["id"], []),
            }
            for m in modules
        ],
        "metadata": {
            "total_modules": len(modules),
            "total_assessments": len(assessments),
            "total_enrolled": len(enrollments),
        },
    }

    return JSONResponse(
        content=lms_export,
        headers={
            "Content-Disposition": f'attachment; filename="course_{course_id}.json"',
            "Content-Type": "application/json",
        },
    )
