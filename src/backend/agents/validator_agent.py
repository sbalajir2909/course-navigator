"""
agents/validator_agent.py
Strict validator — evaluates student explanations against source material only.
Returns structured verdict with pain_point, feedback, and concepts_missed.
"""
from __future__ import annotations
import os, json
from groq import Groq

P_INIT = 0.3
P_LEARN = 0.2
P_SLIP = 0.1
P_GUESS = 0.2

STRATEGY_MAP = {
    1: "direct",
    2: "analogy",
    3: "example",
    4: "decompose",
}

def _bkt_update(prior: float, correct: bool) -> float:
    if correct:
        likelihood = (prior * (1 - P_SLIP)) + ((1 - prior) * P_GUESS)
        posterior = (prior * (1 - P_SLIP)) / likelihood if likelihood > 0 else prior
    else:
        likelihood = (prior * P_SLIP) + ((1 - prior) * (1 - P_GUESS))
        posterior = (prior * P_SLIP) / likelihood if likelihood > 0 else prior
    return posterior + (1 - posterior) * P_LEARN

NON_EXPLANATIONS = {
    "i understand", "i understand ✓", "i get it", "i know", "yes", "ok", "okay",
    "got it", "sure", "yep", "understood", "makes sense", "i think so",
    "i understand this concept well", "i understand this concept", "i don't know",
    "i dont know", "no idea", "not sure", "skip", "pass",
}

def _is_trivial(text: str) -> bool:
    cleaned = text.strip().lower().rstrip("✓ .,!")
    return cleaned in NON_EXPLANATIONS or len(text.strip().split()) < 15

async def validate_explanation(
    student_explanation: str,
    module: dict,
    source_chunks: list[str],
    prior_mastery: float = P_INIT,
    attempt_number: int = 1,
) -> dict:
    """
    Validate student explanation. Returns:
    {
      core_idea, reasoning_quality, own_words, edge_awareness (0-5 each),
      verdict: MASTERED | PARTIAL | NOT_YET,
      pain_point: str,
      feedback_to_student: str,
      concepts_missed: list[str],
      mastery_probability: float,
      advance: bool,
      next_strategy: str,
    }
    """
    # Short-circuit trivial responses
    if _is_trivial(student_explanation):
        new_mastery = _bkt_update(prior_mastery, False)
        next_strategy = STRATEGY_MAP.get(attempt_number + 1, "decompose")
        return {
            "core_idea": 0, "reasoning_quality": 0, "own_words": 0, "edge_awareness": 0,
            "verdict": "NOT_YET",
            "pain_point": "Student did not provide a real explanation — submitted a trivial response.",
            "feedback_to_student": "I need you to explain this concept in your own words — at least 2-3 sentences. What is it, how does it work, and why does it matter?",
            "concepts_missed": [module.get("title", "core concept")],
            "mastery_probability": round(new_mastery, 3),
            "overall_score": 0.0,
            "advance": False,
            "next_strategy": next_strategy,
            "needs_real_explanation": True,
        }

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    source_text = "\n\n".join(chunk[:500] for chunk in source_chunks[:6]) if source_chunks else module.get("description", "No source material.")
    objectives = "\n".join(f"- {o}" for o in module.get("learning_objectives", [])[:4])

    prompt = f"""You are a strict educational validator. Evaluate the student's explanation ONLY against the source material below. Do not use outside knowledge.

MODULE: {module.get("title", "")}
LEARNING OBJECTIVES:
{objectives}

SOURCE MATERIAL (ground truth — evaluate ONLY against this):
{source_text[:3000]}

STUDENT EXPLANATION:
"{student_explanation}"

SCORING RULES (0-5 scale each):
- core_idea: Did they capture the central concept FROM the source? 0=completely wrong/missing, 3=partially correct, 5=accurate and complete
- reasoning_quality: Is their logic coherent and does it follow from the concept? 0=no reasoning, 3=some reasoning, 5=clear causal chain
- own_words: Did they genuinely rephrase (not copy)? 0=verbatim copy or just "I understand", 3=mostly own words, 5=clearly original phrasing
- edge_awareness: Do they show awareness of limitations or nuance? 0=none, 3=some nuance, 5=clear understanding of boundaries

VERDICT RULES (strict):
- MASTERED: average >= 3.5 AND core_idea >= 3
- PARTIAL: average >= 2.0 OR core_idea >= 2
- NOT_YET: anything below PARTIAL, or fewer than 15 words, or says "I don't know"

pain_point: ONE sentence, SPECIFIC — identify exactly what they got wrong or missed.
BAD: "You need to understand this better."
GOOD: "You described the outcome but not the mechanism — you said what MAESTRO does but not how its 7-layer structure works."

feedback_to_student: TWO sentences, SPECIFIC — directly address the pain_point.
BAD: "Good try, keep going."
GOOD: "You correctly identified that MAESTRO addresses AI security gaps — that's the right direction. The missing piece is the specific layers: walk through what each of the 7 layers (Modeling, Analysis, Evaluation, Strategy, Tactics, Operations, Risks) actually does."

concepts_missed: Specific concepts from the source they didn't cover. Not general topics — specific named things.

Return ONLY valid JSON, no extra text:
{{
  "core_idea": 0-5,
  "reasoning_quality": 0-5,
  "own_words": 0-5,
  "edge_awareness": 0-5,
  "verdict": "MASTERED" | "PARTIAL" | "NOT_YET",
  "pain_point": "...",
  "feedback_to_student": "...",
  "concepts_missed": ["specific concept 1", "specific concept 2"]
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=400,
        )
        scores = json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        scores = {
            "core_idea": 1, "reasoning_quality": 1, "own_words": 1, "edge_awareness": 0,
            "verdict": "NOT_YET",
            "pain_point": "Unable to evaluate — please try again with a more detailed explanation.",
            "feedback_to_student": "Something went wrong with the evaluation. Please explain the concept again in 2-3 sentences.",
            "concepts_missed": [],
        }

    # Enforce verdict rules strictly
    avg = (scores.get("core_idea", 0) + scores.get("reasoning_quality", 0) +
           scores.get("own_words", 0) + scores.get("edge_awareness", 0)) / 4.0 / 5.0  # normalize to 0-1

    core = scores.get("core_idea", 0) / 5.0

    if avg >= 0.70 and core >= 0.60:
        verdict = "MASTERED"
    elif avg >= 0.40 or core >= 0.40:
        verdict = "PARTIAL"
    else:
        verdict = "NOT_YET"

    # Override model verdict with rule-based verdict
    scores["verdict"] = verdict

    correct = verdict == "MASTERED"
    new_mastery = _bkt_update(prior_mastery, correct)
    if verdict == "PARTIAL":
        new_mastery = _bkt_update(prior_mastery, True) * 0.6 + prior_mastery * 0.4

    next_attempt = attempt_number + 1
    next_strategy = STRATEGY_MAP.get(next_attempt, "decompose")

    return {
        "core_idea": scores.get("core_idea", 0),
        "reasoning_quality": scores.get("reasoning_quality", 0),
        "own_words": scores.get("own_words", 0),
        "edge_awareness": scores.get("edge_awareness", 0),
        "scores": {
            "core_idea": round(scores.get("core_idea", 0) / 5.0, 2),
            "reasoning_quality": round(scores.get("reasoning_quality", 0) / 5.0, 2),
            "own_words": round(scores.get("own_words", 0) / 5.0, 2),
            "edge_awareness": round(scores.get("edge_awareness", 0) / 5.0, 2),
        },
        "verdict": verdict,
        "pain_point": scores.get("pain_point", ""),
        "feedback_to_student": scores.get("feedback_to_student", ""),
        "concepts_missed": scores.get("concepts_missed", []),
        "mastery_probability": round(new_mastery, 3),
        "overall_score": round(avg, 3),
        "advance": verdict == "MASTERED",
        "next_strategy": next_strategy,
        "needs_real_explanation": False,
    }
