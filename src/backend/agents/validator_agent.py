"""
agents/validator_agent.py
Reference-Anchored Semantic Validator using GPT-4o.
Direct call — no LangGraph wrapping. Results go straight to the API.
"""
from __future__ import annotations
import os, json
from openai import AsyncOpenAI

# Start mastery at 0, not 0.3
P_INIT = 0.0

_client: AsyncOpenAI | None = None

def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


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
    print(f"[VALIDATOR] Called with {len(student_explanation.split())} words, attempt={attempt_number}")

    module_title = module.get("title", "this concept")
    objectives = ", ".join(module.get("learning_objectives", [])[:3])

    # ── Hard reject: too short ────────────────────────────────
    word_count = len(student_explanation.strip().split())
    if word_count < 10:
        print(f"[VALIDATOR] Rejected: too short ({word_count} words)")
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
        print(f"[VALIDATOR] Rejected: non-answer phrase")
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

WHAT THE TEACHING AGENT EXPLAINED:
{agent_trimmed}

SOURCE MATERIAL:
{source_trimmed}

STUDENT'S EXPLANATION:
{student_explanation}

EVALUATION RULES:
- If student captured the core idea correctly → MASTERED (score 8-10)
- If student got main idea but missed nuance → PARTIAL (score 5-7)
- Only if student fundamentally got it wrong → NOT_YET (score 0-4)
- Correct technical vocabulary = understanding, NOT copying
- Do NOT penalize for things not in the source material
- ALWAYS find something correct, even on NOT_YET

Return ONLY this JSON (no markdown, no preamble):
{{
  "understanding_score": <0-10>,
  "verdict": "MASTERED" | "PARTIAL" | "NOT_YET",
  "what_they_got_right": "<one sentence — never empty>",
  "pain_point": "<one sentence about gap if PARTIAL/NOT_YET, empty string if MASTERED>",
  "feedback_to_student": "<two sentences: start positive, then guidance if needed>",
  "concepts_missed": []
}}"""

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a fair, encouraging educator. Find evidence of understanding, not gaps. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        print(f"[VALIDATOR] GPT-4o result: verdict={result.get('verdict')}, score={result.get('understanding_score')}")

    except Exception as e:
        print(f"[VALIDATOR ERROR] GPT-4o failed: {e} — falling back to Groq")
        try:
            from groq import Groq
            gclient = Groq(api_key=os.getenv("GROQ_API_KEY"))
            gr = gclient.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are a fair educator. Find evidence of understanding. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=300,
            )
            result = json.loads(gr.choices[0].message.content)
            print(f"[VALIDATOR] Groq fallback result: verdict={result.get('verdict')}")
        except Exception as e2:
            print(f"[VALIDATOR ERROR] Both LLMs failed: {e2} — returning PARTIAL (never NOT_YET on error)")
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
