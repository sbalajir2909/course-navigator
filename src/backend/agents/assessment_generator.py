"""
agents/assessment_generator.py - Groq version
"""
from __future__ import annotations
import os, json
from groq import Groq

async def generate_assessments(module: dict, source_chunks: list[str]) -> list[dict]:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    source_text = "\n\n".join(source_chunks[:8]) if source_chunks else module.get("description", "")

    prompt = f"""Generate exactly 6 assessment questions for this module. Return ONLY a JSON array.

Module: {module.get('title', '')}
Description: {module.get('description', '')}
Learning Objectives: {json.dumps(module.get('learning_objectives', []))}
Source: {source_text[:2000]}

Return a JSON array of 6 questions (4 multiple_choice, 2 short_answer), 2 recall + 2 application + 2 synthesis:
[
  {{
    "question": "Question text",
    "question_type": "multiple_choice",
    "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
    "correct_answer": "A) option1",
    "difficulty_tier": "recall",
    "source_chunk_indices": [0]
  }}
]"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    raw = json.loads(response.choices[0].message.content.strip())
    if isinstance(raw, dict):
        # unwrap if nested
        for key in ("questions", "assessments", "items"):
            if key in raw:
                return raw[key]
        return list(raw.values())[0] if raw else []
    return raw
