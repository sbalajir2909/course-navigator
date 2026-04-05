"""
agents/assessment_generator.py
"""
from __future__ import annotations
import json
from utils.cf_client import get_cf_client, CF_MODEL_8B
from utils.logger import get_logger

logger = get_logger(__name__)


def _unwrap(raw: object) -> list[dict]:
    """Normalize LLM output into a list of question dicts."""
    if isinstance(raw, list):
        return [a for a in raw if isinstance(a, dict)]
    if isinstance(raw, dict):
        # Unwrap known wrapper keys
        for key in ("questions", "assessments", "items", "data"):
            if key in raw and isinstance(raw[key], list):
                return [a for a in raw[key] if isinstance(a, dict)]
        # Single question dict
        if "question" in raw:
            return [raw]
        # Numbered keys: {"1": {...}, "2": {...}}
        values = list(raw.values())
        if values and all(isinstance(v, dict) for v in values):
            return [v for v in values if "question" in v]
        # First value that is a list of dicts
        for v in values:
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return [a for a in v if isinstance(a, dict)]
    return []


async def generate_assessments(module: dict, source_chunks: list[str]) -> list[dict]:
    client = get_cf_client()
    source_text = "\n\n".join(source_chunks[:8]) if source_chunks else module.get("description", "")

    prompt = f"""Generate exactly 6 assessment questions for this module.

Module: {module.get('title', '')}
Description: {module.get('description', '')}
Learning Objectives: {json.dumps(module.get('learning_objectives', []))}
Source: {source_text[:2000]}

Return a JSON object with a "questions" array of 6 items (4 multiple_choice, 2 short_answer), 2 recall + 2 application + 2 synthesis:
{{
  "questions": [
    {{
      "question": "Question text",
      "question_type": "multiple_choice",
      "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
      "correct_answer": "A) option1",
      "difficulty_tier": "recall",
      "source_chunk_indices": [0]
    }}
  ]
}}"""

    try:
        response = await client.chat.completions.acreate(
            model=CF_MODEL_8B,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
            max_tokens=2000,
        )
        raw = json.loads(response.choices[0].message.content.strip())
        result = _unwrap(raw)
        logger.debug("Assessment generator returned %d questions for '%s'", len(result), module.get('title', ''))
        return result
    except Exception as e:
        logger.error("Assessment generation failed for '%s': %s", module.get('title', ''), e)
        return []
