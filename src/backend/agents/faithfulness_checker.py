"""
agents/faithfulness_checker.py - Groq version
"""
from __future__ import annotations
import os, json
from utils.cf_client import get_cf_client, CF_MODEL_8B

async def check_faithfulness(module: dict, source_chunks: list[str]) -> dict:
    if not source_chunks:
        return {"verdict": "PARTIAL", "details": "No source chunks available.", "unsupported_claims": []}

    client = get_cf_client()
    source_text = "\n\n".join(source_chunks[:8])

    prompt = f"""Check if this module content is faithful to the source material. Return ONLY valid JSON.

Module Title: {module.get('title', '')}
Module Description: {module.get('description', '')}
Learning Objectives: {json.dumps(module.get('learning_objectives', []))}

Source Material:
{source_text}

Return JSON:
{{"verdict": "FAITHFUL", "details": "explanation", "unsupported_claims": []}}

verdict must be FAITHFUL, PARTIAL, or UNFAITHFUL."""

    response = await client.chat.completions.acreate(
        model=CF_MODEL_8B,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content.strip())
