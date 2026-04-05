"""
agents/validator_agent.py - Groq version with strict anti-hallucination rules.
BKT mastery tracking per student.
"""
from __future__ import annotations
import os, json
from groq import Groq

P_INIT = 0.3
P_LEARN = 0.2
P_SLIP = 0.1
P_GUESS = 0.2

def _bkt_update(prior: float, correct: bool) -> float:
    if correct:
        likelihood = (prior * (1 - P_SLIP)) + ((1 - prior) * P_GUESS)
        posterior = (prior * (1 - P_SLIP)) / likelihood if likelihood > 0 else prior
    else:
        likelihood = (prior * P_SLIP) + ((1 - prior) * (1 - P_GUESS))
        posterior = (prior * P_SLIP) / likelihood if likelihood > 0 else prior
    return posterior + (1 - posterior) * P_LEARN

# Phrases that indicate the student hasn't actually explained — short-circuit these
NON_EXPLANATIONS = [
    "i understand", "i understand ✓", "i get it", "i know", "yes", "ok", "okay",
    "got it", "sure", "yep", "understood", "makes sense", "i think so",
    "i understand this concept well", "i understand this concept",
]

def _is_non_explanation(text: str) -> bool:
    """Detect if the student submitted a non-explanation (just clicked a chip)."""
    cleaned = text.strip().lower().rstrip("✓ .,!")
    return cleaned in NON_EXPLANATIONS or len(text.strip().split()) < 6

async def validate_explanation(
    student_explanation: str,
    module: dict,
    source_chunks: list[str],
    prior_mastery: float = P_INIT
) -> dict:
    
    # If student just clicked "I understand" or gave a trivial response,
    # don't call the LLM — give partial credit and ask for a real explanation
    if _is_non_explanation(student_explanation):
        new_mastery = _bkt_update(prior_mastery, False)
        return {
            "scores": {"core_idea": 0.0, "reasoning_quality": 0.0, "own_words": 0.0, "edge_awareness": 0.0},
            "overall_score": 0.0,
            "mastery_probability": round(new_mastery, 3),
            "feedback": "Can you explain this in your own words? I need to see that you actually understand it — a real explanation, not just 'I understand'. Try describing the key concept as if you were explaining it to a friend.",
            "advance": False,
            "needs_real_explanation": True,
        }

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    source_text = "\n\n".join(source_chunks[:5]) if source_chunks else module.get("description", "")

    prompt = f"""You are a strict educational validator. Your job is to check if a student truly understands a concept — not just restated it.

STRICT RULES:
1. Score 0.0 if the student just says "I understand" or vague phrases without explanation
2. Score based ONLY on what the student actually said — do NOT give benefit of the doubt
3. core_idea must be > 0.5 only if student correctly explained the MAIN concept
4. reasoning_quality must be > 0.5 only if student explained WHY, not just WHAT
5. own_words must be > 0.5 only if student used their own language (not copied from the teaching)
6. edge_awareness is a bonus — only > 0.5 if student showed nuance or limitations
7. Minimum total word count for any score above 0: at least 20 words

Module: {module.get('title', '')}
Learning Objectives:
{json.dumps(module.get('learning_objectives', []))}

Source Material (ground truth):
{source_text[:2000]}

Student's Explanation:
"{student_explanation}"

Return ONLY valid JSON, no explanation outside JSON:
{{
  "core_idea": 0.0,
  "reasoning_quality": 0.0,
  "own_words": 0.0,
  "edge_awareness": 0.0,
  "feedback": "Specific, honest feedback (2-3 sentences). Tell them exactly what they got right and what's missing. Be encouraging but truthful."
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Low temperature for consistent scoring
            response_format={"type": "json_object"},
        )
        scores = json.loads(response.choices[0].message.content.strip())
    except Exception:
        # Fallback if LLM fails
        scores = {
            "core_idea": 0.3, "reasoning_quality": 0.2,
            "own_words": 0.3, "edge_awareness": 0.1,
            "feedback": "Good effort! Keep building on this."
        }

    weights = {"core_idea": 0.4, "reasoning_quality": 0.3, "own_words": 0.2, "edge_awareness": 0.1}
    overall = sum(float(scores.get(k, 0)) * w for k, w in weights.items())
    overall = min(1.0, max(0.0, overall))

    # Only advance if genuinely understood (>= 65% overall)
    correct = overall >= 0.65
    new_mastery = _bkt_update(prior_mastery, correct)

    return {
        "scores": {k: round(float(scores.get(k, 0)), 2) for k in weights},
        "overall_score": round(overall, 3),
        "mastery_probability": round(new_mastery, 3),
        "feedback": scores.get("feedback", "Keep going!"),
        "advance": new_mastery >= 0.7 and overall >= 0.65,
        "needs_real_explanation": False,
    }
