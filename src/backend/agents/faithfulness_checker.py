"""
agents/faithfulness_checker.py - Groq version
"""
from __future__ import annotations
import os, json
from groq import Groq

async def check_faithfulness(module: dict, source_chunks: list[str]) -> dict:
    if not source_chunks:
        return {"verdict": "PARTIAL", "details": "No source chunks available.", "unsupported_claims": []}

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
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

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content.strip())
