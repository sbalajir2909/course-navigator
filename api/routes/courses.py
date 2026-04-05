"""
api/routes/courses.py
Course retrieval, enrollment, graph visualization, and assessment access.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import supabase_query

router = APIRouter(prefix="/api/courses", tags=["courses"])


# ─────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────

class ModuleOut(BaseModel):
    id: str
    title: str
    description: str | None
    learning_objectives: list[str]
    order_index: int
    estimated_minutes: int
    source_type: str
    faithfulness_verdict: str | None
    prerequisites: list[str]  # List of prerequisite module UUIDs


class CourseOut(BaseModel):
    id: str
    professor_id: str
    title: str
    description: str | None
    status: str
    modules: list[ModuleOut]


class GraphNode(BaseModel):
    id: str
    data: dict[str, Any]
    position: dict[str, float]
    type: str = "default"


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    animated: bool = False


class CourseGraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class EnrollRequest(BaseModel):
    student_id: str | None = None
    email: str | None = None
    name: str | None = None


class EnrollResponse(BaseModel):
    enrollment_id: str
    student_id: str
    course_id: str


class AssessmentOut(BaseModel):
    id: str
    question: str
    question_type: str
    options: list[str] | None
    correct_answer: str
    difficulty_tier: str


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@router.get("/{course_id}", response_model=CourseOut)
async def get_course(course_id: str) -> CourseOut:
    """
    Return full course details including all modules and their prerequisites.
    """
    courses = await supabase_query(
        "courses",
        params={
            "id": f"eq.{course_id}",
            "select": "id,professor_id,title,description,status",
        },
    )
    if not courses:
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found.")

    course = courses[0]

    # Fetch modules ordered by order_index
    modules_raw = await supabase_query(
        "modules",
        params={
            "course_id": f"eq.{course_id}",
            "select": "id,title,description,learning_objectives,order_index,estimated_minutes,source_type,faithfulness_verdict",
            "order": "order_index.asc",
        },
    )

    # Fetch all prerequisites for this course's modules
    if modules_raw:
        module_ids = [m["id"] for m in modules_raw]
        id_list = "(" + ",".join(module_ids) + ")"
        prereqs_raw = await supabase_query(
            "prerequisites",
            params={
                "module_id": f"in.{id_list}",
                "select": "module_id,prerequisite_module_id",
            },
        )
        # Build map: module_id → list of prereq module UUIDs
        prereq_map: dict[str, list[str]] = {}
        for p in prereqs_raw:
            prereq_map.setdefault(p["module_id"], []).append(p["prerequisite_module_id"])
    else:
        prereq_map = {}

    modules_out = []
    for m in modules_raw:
        modules_out.append(
            ModuleOut(
                id=m["id"],
                title=m["title"],
                description=m.get("description"),
                learning_objectives=m.get("learning_objectives") or [],
                order_index=m.get("order_index", 0),
                estimated_minutes=m.get("estimated_minutes", 30),
                source_type=m.get("source_type", "material"),
                faithfulness_verdict=m.get("faithfulness_verdict"),
                prerequisites=prereq_map.get(m["id"], []),
            )
        )

    return CourseOut(
        id=course["id"],
        professor_id=course["professor_id"],
        title=course["title"],
        description=course.get("description"),
        status=course["status"],
        modules=modules_out,
    )


@router.get("/{course_id}/graph", response_model=CourseGraphOut)
async def get_course_graph(course_id: str) -> CourseGraphOut:
    """
    Return a React Flow–compatible dependency graph for the course.

    Nodes represent modules; edges represent prerequisites.
    Layout uses a simple top-down layered approach based on order_index.
    """
    # Verify course exists
    courses = await supabase_query(
        "courses",
        params={"id": f"eq.{course_id}", "select": "id,title"},
    )
    if not courses:
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found.")

    # Fetch modules
    modules_raw = await supabase_query(
        "modules",
        params={
            "course_id": f"eq.{course_id}",
            "select": "id,title,order_index,estimated_minutes,faithfulness_verdict",
            "order": "order_index.asc",
        },
    )

    if not modules_raw:
        return CourseGraphOut(nodes=[], edges=[])

    # Fetch prerequisites
    module_ids = [m["id"] for m in modules_raw]
    id_list = "(" + ",".join(module_ids) + ")"
    prereqs_raw = await supabase_query(
        "prerequisites",
        params={
            "module_id": f"in.{id_list}",
            "select": "module_id,prerequisite_module_id",
        },
    )

    # Build nodes with simple grid layout (200px columns, 120px rows)
    nodes: list[GraphNode] = []
    COLS = 3
    X_SPACING = 300
    Y_SPACING = 150

    for i, m in enumerate(modules_raw):
        col = i % COLS
        row = i // COLS
        nodes.append(
            GraphNode(
                id=m["id"],
                data={
                    "label": m["title"],
                    "order_index": m.get("order_index", i),
                    "estimated_minutes": m.get("estimated_minutes", 30),
                    "faithfulness_verdict": m.get("faithfulness_verdict"),
                },
                position={"x": col * X_SPACING, "y": row * Y_SPACING},
                type="default",
            )
        )

    # Build edges from prerequisites
    edges: list[GraphEdge] = []
    for p in prereqs_raw:
        edge_id = f"e-{p['prerequisite_module_id']}-{p['module_id']}"
        edges.append(
            GraphEdge(
                id=edge_id,
                source=p["prerequisite_module_id"],  # prereq → module (arrow direction)
                target=p["module_id"],
                animated=False,
            )
        )

    return CourseGraphOut(nodes=nodes, edges=edges)


@router.post("/{course_id}/enroll", response_model=EnrollResponse)
async def enroll_student(course_id: str, body: EnrollRequest) -> EnrollResponse:
    """
    Enroll a student in a course.
    Idempotent: returns existing enrollment if already enrolled.
    """
    student_id = body.student_id

    # Verify course
    courses = await supabase_query(
        "courses",
        params={"id": f"eq.{course_id}", "select": "id"},
    )
    if not courses:
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found.")

    # Auto-create student from email+name if no student_id
    if not student_id:
        email = body.email or "student@demo.com"
        name = body.name or "Demo Student"
        existing_student = await supabase_query(
            "students",
            params={"email": f"eq.{email}", "select": "id"},
        )
        if existing_student:
            student_id = existing_student[0]["id"]
        else:
            student_id = str(uuid.uuid4())
            await supabase_query(
                "students",
                method="POST",
                json={"id": student_id, "email": email, "name": name},
            )
    else:
        students = await supabase_query(
            "students",
            params={"id": f"eq.{student_id}", "select": "id"},
        )
        if not students:
            raise HTTPException(status_code=404, detail=f"Student {student_id} not found.")

    # Check for existing enrollment
    existing = await supabase_query(
        "enrollments",
        params={
            "student_id": f"eq.{student_id}",
            "course_id": f"eq.{course_id}",
            "select": "id",
        },
    )
    if existing:
        return EnrollResponse(
            enrollment_id=existing[0]["id"],
            student_id=student_id,
            course_id=course_id,
        )

    # Create enrollment
    enrollment_id = str(uuid.uuid4())
    await supabase_query(
        "enrollments",
        method="POST",
        json={
            "id": enrollment_id,
            "student_id": student_id,
            "course_id": course_id,
        },
    )

    return EnrollResponse(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
    )


@router.get("/{course_id}/modules/{module_id}/assessments", response_model=list[AssessmentOut])
async def get_module_assessments(course_id: str, module_id: str) -> list[AssessmentOut]:
    """
    Return all assessments for a specific module.

    Validates that the module belongs to the given course.
    """
    # Verify module belongs to course
    modules = await supabase_query(
        "modules",
        params={
            "id": f"eq.{module_id}",
            "course_id": f"eq.{course_id}",
            "select": "id",
        },
    )
    if not modules:
        raise HTTPException(
            status_code=404,
            detail=f"Module {module_id} not found in course {course_id}.",
        )

    assessments_raw = await supabase_query(
        "assessments",
        params={
            "module_id": f"eq.{module_id}",
            "select": "id,question,question_type,options,correct_answer,difficulty_tier",
        },
    )

    return [
        AssessmentOut(
            id=a["id"],
            question=a["question"],
            question_type=a["question_type"],
            options=a.get("options"),
            correct_answer=a["correct_answer"],
            difficulty_tier=a["difficulty_tier"],
        )
        for a in assessments_raw
    ]
