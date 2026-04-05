"""
agents/assessment_generator.py
Primary: Cloudflare @cf/meta/llama-3.1-70b-instruct
Fallback: OpenAI gpt-4o-mini
"""
from __future__ import annotations
import json


async def generate_assessments(module: dict, source_chunks: list[str]) -> list[dict]:
    from api.cf_client import complete_json as cf_json

    source_text = "\n\n".join(source_chunks[:8]) if source_chunks else module.get("description", "")

    # Scale question count: 3 questions per concept, minimum 10, maximum 20
    concepts = module.get("concepts", [])
    n_concepts = max(1, len(concepts))
    n_questions = max(10, min(20, n_concepts * 3))
    n_mcq = (n_questions * 2) // 3      # ~2/3 multiple choice
    n_short = n_questions - n_mcq       # ~1/3 short answer

    # Build concept summary for targeted question generation
    concept_titles = [c.get("title", "") for c in concepts if c.get("title")]
    concept_text = "\n".join(f"- {t}" for t in concept_titles) if concept_titles else "(see description)"

    prompt = f"""Generate exactly {n_questions} assessment questions for this module. Return ONLY a JSON array.

Module: {module.get('title', '')}
Description: {module.get('description', '')}
Concepts covered:
{concept_text}
Learning Objectives: {json.dumps(module.get('learning_objectives', []))}
Source: {source_text[:3000]}

STRICT RULES for multiple_choice options:
1. Every option MUST be a FACTUAL ANSWER about the concept — a short phrase or sentence about the subject matter.
2. Options must NEVER be meta-instructions like "explain in 4 words", "describe briefly", "give an example", "summarize", etc.
3. Only one option is correct. The other three are plausible but wrong.
4. Options should be comparable in length.
5. Options must test conceptual understanding, not recall of exact wording.
6. Each concept should have at least 2 questions targeting it specifically.

Return a JSON array of exactly {n_questions} questions ({n_mcq} multiple_choice, {n_short} short_answer).
Distribute difficulty: ~1/3 recall, ~1/3 application, ~1/3 synthesis.
[
  {{
    "question": "Question text testing understanding",
    "question_type": "multiple_choice",
    "options": ["A) factual answer about the concept", "B) plausible but wrong answer", "C) another wrong answer", "D) another wrong answer"],
    "correct_answer": "A) factual answer about the concept",
    "difficulty_tier": "recall",
    "source_chunk_indices": [0]
  }}
]"""

    raw = await cf_json(
        messages=[{"role": "user", "content": prompt}],
        model_key="course",
        temperature=0.4,
        max_tokens=4000,
    )

    if isinstance(raw, dict):
        for key in ("questions", "assessments", "items"):
            if key in raw:
                return raw[key]
        return list(raw.values())[0] if raw else []
    return raw
