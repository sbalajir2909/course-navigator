"""
api/routes/ingest.py
"""
from __future__ import annotations
import os, uuid
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from api.db import supabase_query
from utils.logger import get_logger

logger = get_logger(__name__)
from utils.parser import parse_file
from utils.chunker import chunk_text
from agents.course_generator import generate_course
from agents.faithfulness_checker import check_faithfulness
from agents.assessment_generator import generate_assessments

router = APIRouter(prefix="/api", tags=["ingest"])

class IngestResponse(BaseModel):
    course_id: str
    status: str

class StatusResponse(BaseModel):
    course_id: str
    status: str
    module_count: int
    assessment_count: int

async def _run_ingest_pipeline(course_id, document_id, file_bytes, filename, chunks_data):
    logger.info("Starting pipeline for course=%s file=%s", course_id, filename)
    try:
        logger.info("Parsing file...")
        raw_text = parse_file(file_bytes, filename)
        logger.info("Parsed %d chars", len(raw_text))
        await supabase_query(f"source_documents?id=eq.{document_id}", method="PATCH", json={"raw_text": raw_text})
        chunks = chunk_text(raw_text)
        logger.info("Created %d chunks", len(chunks))

        chunk_id_map = {}
        for chunk in chunks:
            cid = str(uuid.uuid4())
            chunk_id_map[chunk["chunk_index"]] = cid
            await supabase_query("chunks", method="POST", json={
                "id": cid,
                "course_id": course_id,
                "content": chunk["content"],
                "chunk_index": chunk["chunk_index"],
                "source_document_id": document_id,
            })
        logger.info("Stored %d chunks in DB", len(chunks))

        course_rows = await supabase_query("courses", params={"id": f"eq.{course_id}", "select": "title"})
        course_title = course_rows[0]["title"] if course_rows else "Untitled"
        logger.info("Generating course structure for '%s'...", course_title)
        course_data = await generate_course(chunks, course_title)
        modules_count = len(course_data.get("modules", []))
        logger.info("Generated %d modules", modules_count)
        await supabase_query(f"courses?id=eq.{course_id}", method="PATCH", json={"description": course_data.get("description", "")})

        modules_list = course_data.get("modules", [])

        # First pass: assign UUIDs to all modules
        module_title_to_id = {}
        for mod in modules_list:
            module_title_to_id[mod["title"]] = str(uuid.uuid4())

        # Second pass: save modules with resolved prerequisite UUIDs
        for idx, mod in enumerate(modules_list):
            mid = module_title_to_id[mod["title"]]
            prereq_ids = [
                module_title_to_id[pre]
                for pre in mod.get("prerequisites", [])
                if pre in module_title_to_id
            ]
            logger.info("Saving module %d/%d: %s", idx + 1, len(modules_list), mod["title"])
            await supabase_query("modules", method="POST", json={
                "id": mid,
                "course_id": course_id,
                "title": mod["title"],
                "description": mod.get("description", ""),
                "order_index": idx,
                "concepts": mod.get("concepts", []),
                "prerequisites": prereq_ids,
                "estimated_minutes": mod.get("estimated_minutes", 30),
            })

        chunk_content_map = {c["chunk_index"]: c["content"] for c in chunks}
        for mod in modules_list:
            mid = module_title_to_id.get(mod["title"])
            if not mid:
                continue
            src_texts = [chunk_content_map[i] for i in mod.get("source_chunk_indices", []) if i in chunk_content_map]

            try:
                logger.info("Faithfulness check: %s", mod["title"])
                await check_faithfulness(mod, src_texts)
                # faithfulness results logged only — not in current modules schema
            except Exception as e:
                logger.error("Faithfulness error: %s", e)

            try:
                logger.info("Generating assessments: %s", mod["title"])
                assmts = await generate_assessments(mod, src_texts)
                saved = 0
                for a in assmts:
                    if not isinstance(a, dict):
                        continue
                    question = a.get("question", "")
                    answer = a.get("correct_answer") or a.get("answer", "")
                    if not question or not answer:
                        continue
                    await supabase_query("assessments", method="POST", json={
                        "id": str(uuid.uuid4()),
                        "module_id": mid,
                        "course_id": course_id,
                        "question": question,
                        "question_type": a.get("question_type", "multiple_choice"),
                        "options": a.get("options"),
                        "answer": answer,
                        "reference_explanation": a.get("reference_explanation", ""),
                    })
                    saved += 1
                logger.info("Saved %d assessments for %s", saved, mod["title"])
            except Exception as e:
                logger.error("Assessment error: %s", e)

        await supabase_query(f"courses?id=eq.{course_id}", method="PATCH", json={"status": "ready"})
        logger.info("Course %s is READY", course_id)

    except Exception as exc:
        logger.error("Pipeline FAILED for course %s: %s: %s", course_id, type(exc).__name__, exc)
        try:
            await supabase_query(f"courses?id=eq.{course_id}", method="PATCH", json={"status": "failed"})
        except:
            pass
        raise exc

@router.post("/ingest", response_model=IngestResponse)
async def ingest_file(background_tasks: BackgroundTasks, file: UploadFile = File(...), course_title: str = Form(...), professor_id: str = Form(None), professor_email: str = Form(None)):
    if not professor_id:
        email = professor_email or "demo@assign.ai"
        existing = await supabase_query("professors", params={"email": f"eq.{email}", "select": "id"})
        if existing:
            professor_id = existing[0]["id"]
        else:
            professor_id = str(uuid.uuid4())
            await supabase_query("professors", method="POST", json={"id": professor_id, "email": email, "name": email.split("@")[0]})
    course_id = str(uuid.uuid4())
    await supabase_query("courses", method="POST", json={"id": course_id, "professor_id": professor_id, "title": course_title, "status": "processing"})
    file_bytes = await file.read()
    filename = file.filename or "upload"
    try:
        raw_text_preview = parse_file(file_bytes, filename)
    except ValueError as exc:
        await supabase_query(f"courses?id=eq.{course_id}", method="PATCH", json={"status": "failed"})
        raise HTTPException(status_code=400, detail=str(exc))
    document_id = str(uuid.uuid4())
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
    await supabase_query("source_documents", method="POST", json={
        "id": document_id, "course_id": course_id, "filename": filename,
        "file_type": file_ext, "raw_text": None,
    })
    initial_chunks = chunk_text(raw_text_preview)
    background_tasks.add_task(_run_ingest_pipeline, course_id, document_id, file_bytes, filename, initial_chunks)
    return IngestResponse(course_id=course_id, status="processing")

@router.get("/ingest/{course_id}/status", response_model=StatusResponse)
async def get_ingest_status(course_id: str):
    if not course_id or course_id in ("undefined", "null"):
        raise HTTPException(status_code=400, detail="Invalid course_id.")
    courses = await supabase_query("courses", params={"id": f"eq.{course_id}", "select": "id,status"})
    if not courses:
        raise HTTPException(status_code=404, detail="Course not found.")
    modules = await supabase_query("modules", params={"course_id": f"eq.{course_id}", "select": "id"})
    module_ids = [m["id"] for m in modules]
    assessment_count = 0
    if module_ids:
        assessments = await supabase_query("assessments", params={"module_id": f"in.({','.join(module_ids)})", "select": "id"})
        assessment_count = len(assessments)
    return StatusResponse(course_id=course_id, status=courses[0]["status"], module_count=len(modules), assessment_count=assessment_count)
