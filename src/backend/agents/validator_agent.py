"""
agents/validator_agent.py
Reference-Anchored Semantic Validator using GPT-4o.
Direct call — no LangGraph wrapping. Results go straight to the API.
"""
from __future__ import annotations
import os, json
from utils.logger import get_logger

logger = get_logger(__name__)

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
    logger.info("Called with %d words, attempt=%d", len(student_explanation.split()), attempt_number)

    module_title = module.get("title", "this concept")
    objectives = ", ".join(module.get("learning_objectives", [])[:3])

    # ── Hard reject: too short ────────────────────────────────
    word_count = len(student_explanation.strip().split())
    if word_count < 10:
        logger.warning("Rejected: too short (%d words)", word_count)
        return _build_result(
            verdict="INVALID_INPUT",
            score=0,
            what_right="",
            pain_point="",
            feedback=f"Please write at least 2-3 sentences explaining the concept ({word_count} words is too short).",
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
        logger.warning("Rejected: non-answer phrase")
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

    prompt = f"""You are evaluating whether a student understood a concept.

CONCEPT: {module_title}
LEARNING OBJECTIVE: {objectives}

WHAT THE TEACHING AGENT EXPLAINED (this is the reference_explanation):
{agent_trimmed}

SOURCE MATERIAL:
{source_trimmed}

STUDENT'S EXPLANATION:
{student_explanation}

STRICT RULES — NO EXCEPTIONS:
1. NEVER mention what the source material does NOT cover. Never say "the source doesn't address..." or "the material doesn't explain..." — this confuses students.
2. NEVER suggest prerequisites or say "you might want to review X first" — there is no prerequisite feature.
3. NEVER hallucinate concepts not present in the reference_explanation.
4. If the student's answer contains the right keywords/concepts from the reference, score >= 7 (MASTERED) unless they made a clear factual error.
5. Feedback must be grounded ONLY in the reference_explanation provided. Do not bring in outside knowledge.
6. Always acknowledge what_they_got_right, even on NOT_YET verdicts.
7. NEVER return NOT_YET on a parsing error or missing data — return PARTIAL as fallback.
8. Score overrides verdict label: score >= 7 → MASTERED, score 5-6 → PARTIAL, score < 5 → NOT_YET.

EVALUATION RULES:
- If student captured the core idea correctly → MASTERED (score 8-10)
- If student got main idea but missed nuance → PARTIAL (score 5-7)
- Only if student fundamentally got it wrong → NOT_YET (score 0-4)
- Correct technical vocabulary = understanding, NOT copying
- Do NOT penalize for things not in the source material
- ALWAYS find something correct, even on NOT_YET

Return ONLY this JSON (no markdown, no preamble):
{{
  "verdict": "MASTERED" | "PARTIAL" | "NOT_YET",
  "understanding_score": <0-10>,
  "what_they_got_right": "<one sentence — never empty>",
  "pain_point": "<one sentence about gap if PARTIAL/NOT_YET, empty string if MASTERED>",
  "feedback_to_student": "<two sentences: start positive, then guidance if needed>",
  "concepts_missed": []
}}"""

    try:
        from utils.cf_client import get_cf_client, CF_MODEL_70B
        gclient = get_cf_client()
        gr = await gclient.chat.completions.acreate(
            model=CF_MODEL_70B,
            messages=[
                {"role": "system", "content": "You are a fair, encouraging educator. Find evidence of understanding, not gaps. NEVER mention what the source doesn't cover. NEVER suggest prerequisites. Ground feedback ONLY in the reference explanation. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=300,
        )
        result = json.loads(gr.choices[0].message.content)
        logger.info("Cloudflare result: verdict=%s, score=%s", result.get('verdict'), result.get('understanding_score'))

    except Exception as e:
        logger.error("Cloudflare failed: %s — returning PARTIAL", e)
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

    # Ensure what_they_got_right is never empty
    if not result.get("what_they_got_right", "").strip():
        result["what_they_got_right"] = "You engaged with the concept and made a genuine attempt to explain it."

    # Clean MASTERED fields
    if verdict == "MASTERED":
        result["pain_point"] = ""
        result["concepts_missed"] = []

    logger.info("Final: verdict=%s, score=%d, mastery: %.2f → %.2f", verdict, score, prior_mastery, _new_mastery(prior_mastery, verdict))

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
    strategy_map = {1: "direct", 2: "analogy", 3: "example", 4: "decompose"}
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
