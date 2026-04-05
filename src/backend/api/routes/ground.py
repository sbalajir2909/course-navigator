"""
api/routes/ground.py
Tavily-powered web grounding for modules with gaps or parametric source_type.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import supabase_query

router = APIRouter(prefix="/api/ground", tags=["ground"])


# ─────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────

class GroundedResult(BaseModel):
    module_id: str
    module_title: str
    query_used: str
    results: list[dict[str, Any]]   # [{title, url, content, score}]
    synthesis: str                  # AI-generated summary with citations


class CourseGroundResponse(BaseModel):
    course_id: str
    grounded_modules: list[GroundedResult]
    skipped_modules: list[str]  # Module IDs skipped (not parametric)


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

async def _tavily_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Execute a Tavily search and return results.

    Args:
        query:       Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of result dicts: [{title, url, content, score}]

    Raises:
        RuntimeError: If Tavily API call fails.
    """
    try:
        from tavily import TavilyClient
    except ImportError:
        raise RuntimeError("tavily-python is not installed. Run: pip install tavily-python")

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set in environment variables.")

    client = TavilyClient(api_key=api_key)

    try:
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Tavily search failed: {exc}") from exc

    results: list[dict[str, Any]] = []
    for r in response.get("results", []):
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
            }
        )

    return results


async def _synthesize_with_citations(
    module: dict[str, Any],
    search_results: list[dict[str, Any]],
) -> str:
    """
    Use GPT-4o to synthesize search results into a coherent enrichment summary
    with inline citations.

    Args:
        module:         Module dict with title, description, learning_objectives.
        search_results: List of Tavily result dicts.

    Returns:
        Synthesis text with inline citations.
    """
    import json as jsonlib
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Format search results for the prompt
    formatted_results: list[str] = []
    for i, r in enumerate(search_results):
        formatted_results.append(
            f"[Source {i + 1}] {r['title']}\nURL: {r['url']}\n{r['content'][:500]}"
        )
    sources_text = "\n\n".join(formatted_results)

    objectives_text = "\n".join(
        f"  - {obj}" for obj in module.get("learning_objectives", [])
    )
    module_summary = (
        f"Title: {module.get('title', '')}\n"
        f"Description: {module.get('description', '')}\n"
        f"Learning Objectives:\n{objectives_text}"
    )

    system_prompt = (
        "You are an expert educational content curator. Given web search results and a module description, "
        "synthesize the most relevant supplementary information into a concise enrichment summary. "
        "Include inline citations like [Source 1], [Source 2] wherever you use information from a source. "
        "Focus on filling gaps in the module's coverage or providing real-world examples."
    )

    user_prompt = (
        f"Module to enrich:\n{module_summary}\n\n"
        f"Web search results:\n{sources_text}\n\n"
        "Write a 200-300 word enrichment summary with inline citations. "
        "Include a 'Sources' list at the end with numbered URLs."
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=800,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        return f"[Synthesis failed: {exc}]"


async def _ground_single_module(module_id: str) -> GroundedResult:
    """
    Ground a single module using Tavily web search.

    Constructs a query from the module title and learning objectives,
    searches the web, and synthesizes enrichment content.

    Args:
        module_id: UUID of the module.

    Returns:
        GroundedResult with search results and synthesis.

    Raises:
        HTTPException: If module not found.
        RuntimeError: If Tavily search fails.
    """
    modules = await supabase_query(
        "modules",
        params={
            "id": f"eq.{module_id}",
            "select": "id,title,description,learning_objectives,faithfulness_verdict,faithfulness_details",
        },
    )
    if not modules:
        raise HTTPException(status_code=404, detail=f"Module {module_id} not found.")

    module = modules[0]

    # Build a targeted search query
    title = module.get("title", "")
    objectives = module.get("learning_objectives") or []
    unsupported_claims: list[str] = []

    faith_details = module.get("faithfulness_details") or {}
    if isinstance(faith_details, dict):
        unsupported_claims = faith_details.get("unsupported_claims", [])

    # Prioritize searching for unsupported claims if available
    if unsupported_claims:
        gap_query = unsupported_claims[0][:120]
        query = f"{title}: {gap_query}"
    elif objectives:
        # Use first learning objective
        first_obj = objectives[0][:80] if objectives else title
        query = f"{title} {first_obj}"
    else:
        query = title

    search_results = await _tavily_search(query, max_results=5)

    synthesis = await _synthesize_with_citations(module, search_results)

    return GroundedResult(
        module_id=module_id,
        module_title=title,
        query_used=query,
        results=search_results,
        synthesis=synthesis,
    )


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@router.post("/{module_id}", response_model=GroundedResult)
async def ground_module(module_id: str) -> GroundedResult:
    """
    Use Tavily to find supplementary web content for a specific module.

    Targets modules that have faithfulness gaps (PARTIAL or UNFAITHFUL verdict)
    or simply need real-world examples to supplement theoretical content.
    """
    try:
        return await _ground_single_module(module_id)
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/course/{course_id}", response_model=CourseGroundResponse)
async def ground_course(course_id: str) -> CourseGroundResponse:
    """
    Ground all modules in a course that have source_type='parametric'.

    Also grounds any module with faithfulness_verdict in ('PARTIAL', 'UNFAITHFUL').

    Returns enriched content with URLs and citations for each grounded module.
    """
    # Verify course
    courses = await supabase_query(
        "courses",
        params={"id": f"eq.{course_id}", "select": "id,title"},
    )
    if not courses:
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found.")

    # Fetch modules that need grounding
    all_modules = await supabase_query(
        "modules",
        params={
            "course_id": f"eq.{course_id}",
            "select": "id,source_type,faithfulness_verdict",
            "order": "order_index.asc",
        },
    )

    target_module_ids: list[str] = []
    skipped_module_ids: list[str] = []

    for m in all_modules:
        source_type = m.get("source_type", "material")
        verdict = m.get("faithfulness_verdict", "FAITHFUL")
        needs_grounding = (
            source_type == "parametric"
            or verdict in ("PARTIAL", "UNFAITHFUL")
        )
        if needs_grounding:
            target_module_ids.append(m["id"])
        else:
            skipped_module_ids.append(m["id"])

    grounded_results: list[GroundedResult] = []
    for module_id in target_module_ids:
        try:
            result = await _ground_single_module(module_id)
            grounded_results.append(result)
        except (RuntimeError, HTTPException):
            # Skip individual failures; log skipped
            skipped_module_ids.append(module_id)

    return CourseGroundResponse(
        course_id=course_id,
        grounded_modules=grounded_results,
        skipped_modules=skipped_module_ids,
    )
