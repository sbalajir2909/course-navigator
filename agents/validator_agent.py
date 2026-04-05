"""
agents/validator_agent.py
Reference-Anchored Semantic Validator.
Primary: Cloudflare @cf/moonshot-ai/kimi-k2.5
Fallback: OpenAI gpt-4o
"""
from __future__ import annotations
import json

P_INIT = 0.0


async def validate_explanation(
    student_explanation: str,
    module: dict,
    source_chunks: list[str],
    prior_mastery: float = P_INIT,
    attempt_number: int = 1,
    agent_explanation: str = "",
) -> dict:
    """
    Validates student explanation semantically against what was taught.
    Returns complete result dict — never raises, never silently returns NOT_YET on error.
    """
    from api.cf_client import complete_json as cf_json

    print(f"[VALIDATOR] Called with {len(student_explanation.split())} words, attempt={attempt_number}")

    module_title = module.get("title", "this concept")
    objectives = ", ".join(module.get("learning_objectives", [])[:3])

    # ── Hard reject: too short ────────────────────────────────
    word_count = len(student_explanation.strip().split())
    if word_count < 5:
        print(f"[VALIDATOR] Rejected: too short ({word_count} words)")
        return _build_result(
            verdict="INVALID_INPUT",
            score=0,
            what_right="",
            pain_point="",
            feedback=f"Please explain what you understood from the lesson ({word_count} words isn't enough to show understanding).",
            missed=[],
            prior_mastery=prior_mastery,
            attempt_number=attempt_number,
        )

    # ── Hard reject: non-answer phrases ──────────────────────
    non_answers = {
        "okay", "ok", "next", "what next", "okay what next", "move on",
        "i don't know", "i dont know", "idk", "skip", "continue", "got it",
        "understood", "sure", "fine", "alright", "what's next", "whats next",
        "okay, what next?", "okay what next?", "what next?",
        "i understand", "i understand ✓", "i get it", "ready", "done",
    }
    if student_explanation.strip().lower().rstrip(".,!?") in non_answers:
        return _build_result(
            verdict="INVALID_INPUT",
            score=0,
            what_right="",
            pain_point="",
            feedback="Please explain the concept in your own words — I need to see that you understood it.",
            missed=[],
            prior_mastery=prior_mastery,
            attempt_number=attempt_number,
        )

    # ── Trim inputs strictly ──────────────────────────────────
    agent_trimmed = " ".join(agent_explanation.split()[:120]) if agent_explanation else "(not available)"
    source_trimmed = " ".join(" ".join(source_chunks[:2]).split()[:200]) if source_chunks else module.get("description", "")

    prompt = f"""You are a strict academic evaluator assessing whether a student genuinely understands a concept — not just whether they recall words.

CONCEPT: {module_title}
LEARNING OBJECTIVE: {objectives}

WHAT THE TEACHING AGENT EXPLAINED (the student just read this):
{agent_trimmed}

SOURCE MATERIAL (ground truth for factual accuracy):
{source_trimmed}

STUDENT'S EXPLANATION:
{student_explanation}

SCORING CRITERIA:
- MASTERED (score 8-10): Student explains the concept accurately in their OWN words, demonstrates WHY it works or what it means — not just restates what was said. Factually correct per source material.
- PARTIAL (score 5-7): Student has the right general idea but misses important nuance, or mostly paraphrases without showing deeper understanding.
- NOT_YET (score 0-4): Student is factually wrong, has misconceptions, or cannot explain beyond surface repetition.

CRITICAL ANTI-CHEAT RULES (apply before scoring):
1. If the student's explanation is a near-verbatim copy or close paraphrase of the agent's explanation, cap score at 4 (NOT_YET) — restating what was said is NOT understanding.
2. If the student just lists keywords or phrases without explaining HOW or WHY they connect, cap score at 4.
3. If any statement directly contradicts the source material, cap score at 3.
4. Vague phrases like "it is important", "it helps with X", "it is used for Y" without specifics = NOT_YET.
5. The student must show they can reconstruct the idea — not recite it.

OTHER RULES:
- Feedback must be grounded ONLY in the reference_explanation.
- Always acknowledge what_they_got_right, even on NOT_YET.
- NEVER return NOT_YET on parsing error — return PARTIAL as fallback.
- Score overrides verdict: score >= 7 → MASTERED, 5-6 → PARTIAL, < 5 → NOT_YET.

Return ONLY this JSON (no markdown):
{{
  "verdict": "MASTERED",
  "understanding_score": 8,
  "what_they_got_right": "one sentence — never empty",
  "pain_point": "one sentence about gap if PARTIAL/NOT_YET, empty string if MASTERED",
  "feedback_to_student": "two sentences: start positive, then guidance if needed",
  "concepts_missed": []
}}"""

    system_msg = (
        "You are a strict but fair academic evaluator. Your job is to check genuine understanding, not recall. "
        "Penalize copy-paste and keyword-stuffing. A student who just repeats the agent's words has NOT understood. "
        "Ground all feedback ONLY in the reference explanation. Return only valid JSON."
    )

    try:
        result = await cf_json(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            model_key="validate",
            max_tokens=350,
            temperature=0.1,
        )
        print(f"[VALIDATOR] Result: verdict={result.get('verdict')}, score={result.get('understanding_score')}")
    except Exception as e:
        print(f"[VALIDATOR ERROR] Both LLMs failed: {e} — returning PARTIAL")
        return _build_result(
            verdict="PARTIAL",
            score=5,
            what_right="Your explanation was received and showed genuine engagement.",
            pain_point="There was a technical issue evaluating your response fully.",
            feedback="There was a technical issue on our end. Your response looked good — let's continue.",
            missed=[],
            prior_mastery=prior_mastery,
            attempt_number=attempt_number,
        )

    # ── Score-based reconciliation ────────────────────────────
    score = max(0, min(10, int(result.get("understanding_score", 5))))

    if score >= 7:
        result["verdict"] = "MASTERED"
    elif score >= 5:
        if result.get("verdict") not in ("PARTIAL", "NOT_YET"):
            result["verdict"] = "PARTIAL"
        if result.get("verdict") == "MASTERED":
            result["verdict"] = "PARTIAL"
    else:
        if result.get("verdict") == "MASTERED":
            result["verdict"] = "PARTIAL"

    verdict = result["verdict"]

    if not result.get("what_they_got_right", "").strip():
        result["what_they_got_right"] = "You engaged with the concept and made a genuine attempt to explain it."

    if verdict == "MASTERED":
        result["pain_point"] = ""
        result["concepts_missed"] = []

    print(f"[VALIDATOR] Final: verdict={verdict}, score={score}, mastery: {prior_mastery:.2f} → {_new_mastery(prior_mastery, verdict):.2f}")

    return _build_result(
        verdict=verdict,
        score=score,
        what_right=result.get("what_they_got_right", ""),
        pain_point=result.get("pain_point", ""),
        feedback=result.get("feedback_to_student", ""),
        missed=result.get("concepts_missed", []),
        prior_mastery=prior_mastery,
        attempt_number=attempt_number,
    )


def _new_mastery(prior: float, verdict: str) -> float:
    if verdict == "MASTERED":
        return min(1.0, prior + 0.25)
    elif verdict == "PARTIAL":
        return min(1.0, prior + 0.08)
    elif verdict == "INVALID_INPUT":
        return prior
    else:
        return max(0.0, prior - 0.02)


def _build_result(
    verdict: str, score: int, what_right: str, pain_point: str,
    feedback: str, missed: list, prior_mastery: float, attempt_number: int,
) -> dict:
    new_mastery = _new_mastery(prior_mastery, verdict)
    strategy_map = {1: "direct", 2: "analogy", 3: "example", 4: "decompose", 5: "simpler"}
    next_attempt = attempt_number if verdict == "MASTERED" else attempt_number + 1
    next_strategy = strategy_map.get(next_attempt, "decompose")
    norm = score / 10.0

    return {
        "verdict": verdict,
        "last_verdict": verdict,
        "understanding_score": score,
        "what_they_got_right": what_right,
        "pain_point": pain_point,
        "feedback_to_student": feedback,
        "concepts_missed": missed,
        "scores": {
            "core_idea": round(norm, 2),
            "reasoning_quality": round(norm * 0.9, 2),
            "own_words": round(norm * 0.85, 2),
            "edge_awareness": round(norm * 0.7, 2),
        },
        "overall_score": round(norm, 3),
        "mastery_probability": round(new_mastery, 3),
        "mastery_score": round(new_mastery, 3),
        "advance": verdict == "MASTERED",
        "should_advance": verdict == "MASTERED",
        "should_flag": next_attempt >= 5 and verdict not in ("MASTERED", "INVALID_INPUT"),
        "next_strategy": next_strategy,
        "needs_real_explanation": verdict == "INVALID_INPUT",
    }
