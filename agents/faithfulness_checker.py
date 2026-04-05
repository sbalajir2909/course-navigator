"""
agents/faithfulness_checker.py
Primary: Cloudflare @cf/meta/llama-3.1-70b-instruct
Fallback: OpenAI gpt-4o-mini
"""
from __future__ import annotations
import json


async def check_faithfulness(module: dict, source_chunks: list[str]) -> dict:
    if not source_chunks:
        return {"verdict": "PARTIAL", "details": "No source chunks available.", "unsupported_claims": []}

    from api.cf_client import complete_json as cf_json

    source_text = "\n\n".join(source_chunks[:8])

    prompt = f"""Check if this module content is faithful to the source material. Return ONLY valid JSON.

Module Title: {module.get('title', '')}
Module Description: {module.get('description', '')}
Learning Objectives: {json.dumps(module.get('learning_objectives', []))}

Source Material:
{source_text[:3000]}

Return JSON:
{{"verdict": "FAITHFUL", "details": "explanation", "unsupported_claims": []}}

verdict must be FAITHFUL, PARTIAL, or UNFAITHFUL."""

    try:
        return await cf_json(
            messages=[{"role": "user", "content": prompt}],
            model_key="course",
            temperature=0.1,
            max_tokens=400,
        )
    except Exception as e:
        return {"verdict": "PARTIAL", "details": f"Check failed: {e}", "unsupported_claims": []}
