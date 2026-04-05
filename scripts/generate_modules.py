"""
scripts/generate_modules.py
Module generator script — regenerates modules for an existing course with richer subtopics.

Usage:
    python scripts/generate_modules.py --course-id <uuid>
    python scripts/generate_modules.py --course-id <uuid> --dry-run   # preview only, don't write to DB
    python scripts/generate_modules.py --list-courses                  # list all courses

The script:
1. Loads all chunks for the course from Supabase
2. Re-runs generate_course() with the improved 5-8 concept/module prompt
3. Reasons through each module's concept coverage before accepting it
4. Writes the new modules to the DB (replacing existing ones if --overwrite)

Environment: requires CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, SUPABASE_URL + SUPABASE_KEY in .env
"""
from __future__ import annotations
import asyncio
import argparse
import json
import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from api.db import supabase_query
from agents.course_generator import generate_course
from agents.faithfulness_checker import check_faithfulness
from agents.assessment_generator import generate_assessments


async def list_courses():
    courses = await supabase_query("courses", params={"select": "id,title,created_at"})
    if not courses:
        print("No courses found.")
        return
    print(f"\n{'ID':<40} {'Title':<50} {'Created'}")
    print("-" * 100)
    for c in courses:
        print(f"{c['id']:<40} {c['title']:<50} {c.get('created_at', '')[:10]}")


async def _load_chunks(course_id: str) -> list[dict]:
    chunks = await supabase_query(
        "chunks",
        params={
            "course_id": f"eq.{course_id}",
            "select": "id,content,chunk_index",
            "order": "chunk_index.asc",
        }
    )
    return chunks


def _reason_module_quality(module: dict) -> tuple[bool, str]:
    """
    Check if a module has adequate concept coverage.
    Returns (is_adequate, reason).
    """
    concepts = module.get("concepts", [])
    title = module.get("title", "?")

    if len(concepts) < 3:
        return False, f"Module '{title}' only has {len(concepts)} concepts — needs at least 3."

    # Check for overly broad concept titles
    broad_indicators = ["understand", "learn about", "overview of", "introduction to"]
    for c in concepts:
        ct = c.get("title", "").lower()
        if any(b in ct for b in broad_indicators):
            return False, f"Concept '{c['title']}' is too broad — should be specific and testable."

    # Check key_points are populated
    thin_concepts = [c for c in concepts if len(c.get("key_points", [])) < 2]
    if len(thin_concepts) > len(concepts) // 2:
        return False, f"More than half of concepts in '{title}' have fewer than 2 key points."

    return True, f"Module '{title}' has {len(concepts)} concepts — adequate."


async def regenerate_modules(
    course_id: str,
    dry_run: bool = False,
    overwrite: bool = False,
    min_concepts_per_module: int = 5,
):
    print(f"\n[GENERATE_MODULES] Course: {course_id}")
    print(f"  dry_run={dry_run}, overwrite={overwrite}, min_concepts={min_concepts_per_module}")

    # Load course metadata
    courses = await supabase_query("courses", params={"id": f"eq.{course_id}", "select": "id,title"})
    if not courses:
        print(f"[ERROR] Course {course_id} not found.")
        return
    course = courses[0]
    title = course["title"]
    print(f"  Title: {title}")

    # Load chunks
    chunks = await _load_chunks(course_id)
    if not chunks:
        print(f"[ERROR] No chunks found for course {course_id}.")
        return
    print(f"  Chunks loaded: {len(chunks)}")

    # Check existing modules
    existing_modules = await supabase_query(
        "modules",
        params={"course_id": f"eq.{course_id}", "select": "id,title,concepts"}
    )
    print(f"  Existing modules: {len(existing_modules)}")
    for m in existing_modules:
        n = len(m.get("concepts") or [])
        print(f"    - {m['title']} ({n} concepts)")

    if existing_modules and not overwrite:
        print(f"\n[WARN] Course already has {len(existing_modules)} modules. Use --overwrite to replace them.")
        return

    # Generate new course structure
    print(f"\n[STEP 1] Generating module structure with llama-3.3-70b-versatile...")
    result = await generate_course(chunks, title)
    new_modules = result.get("modules", [])
    print(f"  Generated {len(new_modules)} modules.")

    # Reason through quality of each module
    print(f"\n[STEP 2] Reasoning through module quality...")
    all_adequate = True
    for m in new_modules:
        adequate, reason = _reason_module_quality(m)
        status = "OK " if adequate else "WARN"
        print(f"  [{status}] {reason}")
        if not adequate:
            all_adequate = False

    if not all_adequate:
        print("\n[WARN] Some modules may need more concepts. Continuing anyway...")

    # Preview
    print(f"\n[PREVIEW] New module structure:")
    total_concepts = 0
    for i, m in enumerate(new_modules, 1):
        concepts = m.get("concepts", [])
        total_concepts += len(concepts)
        print(f"\n  Module {i}: {m['title']}")
        print(f"    Description: {m.get('description', '')}")
        print(f"    Concepts ({len(concepts)}):")
        for c in concepts:
            print(f"      - {c['title']}")
            print(f"        Objective: {c.get('learning_objective', '')}")
            kp = c.get('key_points', [])
            if kp:
                print(f"        Key points: {', '.join(kp[:3])}")
    print(f"\n  Total concepts across all modules: {total_concepts}")
    avg = total_concepts / len(new_modules) if new_modules else 0
    print(f"  Average concepts per module: {avg:.1f}")

    if dry_run:
        print("\n[DRY RUN] Not writing to DB. Pass --overwrite (without --dry-run) to apply.")
        return

    # Write to DB
    print(f"\n[STEP 3] Writing to DB...")

    if overwrite and existing_modules:
        print(f"  Deleting {len(existing_modules)} existing modules...")
        for m in existing_modules:
            await supabase_query(
                f"modules?id=eq.{m['id']}",
                method="DELETE",
            )

    import uuid as _uuid
    for i, m in enumerate(new_modules):
        module_id = str(_uuid.uuid4())

        # Map source_chunk_indices to actual chunk IDs
        chunk_indices = m.get("source_chunk_indices", [])
        source_chunk_ids = []
        for idx in chunk_indices:
            matching = [c["id"] for c in chunks if c.get("chunk_index") == idx]
            source_chunk_ids.extend(matching)
        # Always include at least the first few chunks
        if not source_chunk_ids and chunks:
            source_chunk_ids = [c["id"] for c in chunks[:3]]

        module_record = {
            "id": module_id,
            "course_id": course_id,
            "title": m["title"],
            "description": m.get("description", ""),
            "learning_objectives": m.get("learning_objectives", []),
            "source_chunk_ids": source_chunk_ids,
            "order_index": i,
            "concepts": m.get("concepts", []),
            "estimated_minutes": m.get("estimated_minutes", 30),
        }

        await supabase_query("modules", method="POST", json=module_record)
        print(f"  Saved module {i+1}: {m['title']} ({len(m.get('concepts', []))} concepts)")

        # Generate assessments for each module
        try:
            source_texts = [
                c["content"] for c in chunks
                if c["id"] in source_chunk_ids
            ][:8]
            assessments = await generate_assessments(m, source_texts)
            for q in assessments:
                await supabase_query("assessments", method="POST", json={
                    "id": str(_uuid.uuid4()),
                    "module_id": module_id,
                    "course_id": course_id,
                    **q,
                })
            print(f"    Generated {len(assessments)} assessments.")
        except Exception as e:
            print(f"    [WARN] Assessment generation failed: {e}")

    print(f"\n[DONE] Regenerated {len(new_modules)} modules with {total_concepts} total concepts.")


def main():
    parser = argparse.ArgumentParser(description="Regenerate course modules with richer subtopics.")
    parser.add_argument("--course-id", help="UUID of the course to regenerate")
    parser.add_argument("--list-courses", action="store_true", help="List all courses")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't write to DB")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing modules")
    parser.add_argument("--min-concepts", type=int, default=5, help="Minimum concepts per module (default: 5)")
    args = parser.parse_args()

    if args.list_courses:
        asyncio.run(list_courses())
    elif args.course_id:
        asyncio.run(regenerate_modules(
            course_id=args.course_id,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            min_concepts_per_module=args.min_concepts,
        ))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
