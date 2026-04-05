"""
agents/validator_agent.py
Reference-Anchored Semantic Validator using GPT-4o.

Two-stage pipeline:
1. Generate/retrieve a reference answer for the module
2. Compare student explanation semantically against the reference

This replaces abstract rubric scoring which systematically underestimates correct answers.
"""
from __future__ import annotations
import os, json
from openai import AsyncOpenAI
from api.db import supabase_query

# BKT constants (kept for mastery probability tracking)
P_INIT = 0.3

# In-memory cache for reference explanations (module_id -> reference_text)
_reference_cache: dict[str, str] = {}

VALIDATOR_SYSTEM_PROMPT = """You are an expert educator evaluating whether a student understood a concept.

Your job is NOT to find everything they got wrong.
Your job is to determine if they understood the CORE idea.

EVALUATION PHILOSOPHY:
- A student who explains the core concept correctly in simple terms has understood it.
- A student who uses correct domain vocabulary correctly has understood it.
- A student should NOT be penalized for not mentioning things that weren't taught.
- A student should NOT be penalized for using the same technical terms as the source material.
- Different words conveying the same correct meaning = full credit.
- Partial understanding = partial credit. Not zero credit.

CRITICAL RULES:
1. If the student's explanation conveys the same core meaning as the reference answer, even in completely different words → MASTERED
2. If the student got the main idea right but missed nuance → PARTIAL
3. Only if the student fundamentally misunderstood or missed the core concept → NOT_YET
4. If the student wrote fewer than 15 meaningful words → NOT_YET
5. NEVER penalize for not mentioning things the reference answer doesn't mention either.
6. Using correct technical terminology is a POSITIVE signal, not evidence of copying.

Return ONLY valid JSON. No markdown. No preamble."""


async def _get_or_generate_reference(
    module_id: str,
    module: dict,
    source_chunks: list[str],
) -> str:
    """Get reference explanation from cache/DB or generate on-the-fly."""
    # Check in-memory cache first
    if module_id in _reference_cache:
        return _reference_cache[module_id]

    # Check DB
    try:
        rows = await supabase_query(
            "assessments",
            params={"module_id": f"eq.{module_id}", "select": "reference_explanation", "limit": "1"},
        )
        if rows and rows[0].get("reference_explanation"):
            ref = rows[0]["reference_explanation"]
            _reference_cache[module_id] = ref
            return ref
    except Exception:
        pass

    # Generate on-the-fly with GPT-4o-mini
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    module_content = "\n\n".join(chunk[:400] for chunk in source_chunks[:3]) if source_chunks else module.get("description", "")
    objectives = ", ".join(module.get("learning_objectives", [])[:3])

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"""Based on this module content:
{module_content[:1000]}

Learning objective: {objectives}

Write a model student explanation (3-5 sentences) of '{module.get("title", "this concept")}'.
Write it as a student explaining to a peer — not as a textbook definition.
Show the core concept, why it matters, and one concrete implication.
Use simple language. Do not add information not in the source material."""
            }],
            max_tokens=200,
            temperature=0.3,
        )
        reference = response.choices[0].message.content.strip()
    except Exception:
        # Fallback: use module description as reference
        reference = module.get("description", f"A correct explanation of {module.get('title', 'this concept')} would cover: {objectives}")

    _reference_cache[module_id] = reference

    # Cache in DB asynchronously (non-blocking)
    try:
        await supabase_query(
            f"assessments?module_id=eq.{module_id}",
            method="PATCH",
            json={"reference_explanation": reference},
        )
    except Exception:
        pass

    return reference


async def validate_explanation(
    student_explanation: str,
    module: dict,
    source_chunks: list[str],
    prior_mastery: float = P_INIT,
    attempt_number: int = 1,
    agent_explanation: str = "",
) -> dict:
    """
    Reference-anchored semantic validation using GPT-4o.

    Returns full result dict compatible with both old and new field names.
    """
    module_id = module.get("id", module.get("module_id", ""))
    module_title = module.get("title", "this concept")
    objectives = ", ".join(module.get("learning_objectives", [])[:3])

    # ── Short-circuit trivial/empty responses ──────────────────
    word_count = len(student_explanation.strip().split())
    trivial_phrases = {
        "i don't know", "i dont know", "not sure", "no idea", "idk",
        "i'm not sure", "i understand", "i understand ✓", "i get it",
        "yes", "ok", "okay", "got it", "understood", "skip", "pass",
    }
    cleaned = student_explanation.strip().lower().rstrip("✓ .,!")
    if cleaned in trivial_phrases or word_count < 10:
        return _build_result(
            verdict="NOT_YET",
            score=0,
            pain_point="No real explanation was provided.",
            feedback="Please explain the concept in your own words — at least 2-3 sentences showing what you understood. What does this concept do and why does it matter?",
            what_right="",
            concepts_missed=[module_title],
            prior_mastery=prior_mastery,
            attempt_number=attempt_number,
        )

    # ── Get reference answer ────────────────────────────────────
    reference = await _get_or_generate_reference(module_id, module, source_chunks)

    # ── Build source context (limited to avoid token overflow) ──
    source_context = "\n---\n".join(chunk[:400] for chunk in source_chunks[:2]) if source_chunks else module.get("description", "")

    # ── Call GPT-4o for semantic validation ─────────────────────
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""CONCEPT BEING TAUGHT: {module_title}
LEARNING OBJECTIVE: {objectives}

WHAT THE TEACHING AGENT EXPLAINED TO THE STUDENT:
{agent_explanation[:600] if agent_explanation else "(not available)"}

REFERENCE ANSWER (what a correct student explanation looks like):
{reference}

SOURCE MATERIAL (what was available to teach from):
{source_context[:500]}

STUDENT'S EXPLANATION (attempt {attempt_number} of 5):
{student_explanation}

Evaluate: Does the student's explanation demonstrate understanding of the core concept?

Compare semantically to the REFERENCE ANSWER.
Ask: "Does the student's explanation convey the same core meaning, even in different words?"

Score 0-10 for understanding:
- 8-10: Student clearly understood — covers core idea, may use different words
- 5-7: Student partially understood — got main idea, missed some nuance
- 2-4: Student has some awareness but fundamental gaps
- 0-1: Student did not demonstrate understanding

Verdict rules:
- understanding_score >= 7 → MASTERED
- understanding_score 4-6 → PARTIAL
- understanding_score <= 3 → NOT_YET

Return JSON:
{{
  "verdict": "MASTERED",
  "understanding_score": 8,
  "pain_point": "",
  "feedback_to_student": "You clearly understood the core concept. Well done.",
  "concepts_missed": [],
  "what_they_got_right": "You correctly explained that threat modeling is a systematic process for identifying vulnerabilities in agentic AI systems before they are exploited."
}}"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
    except Exception as e:
        # Fallback: use Groq if OpenAI fails
        try:
            from groq import Groq
            gclient = Groq(api_key=os.getenv("GROQ_API_KEY"))
            gr = gclient.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=400,
            )
            result = json.loads(gr.choices[0].message.content)
        except Exception:
            # Last resort: give partial credit if explanation is substantive
            result = {
                "verdict": "PARTIAL",
                "understanding_score": 5,
                "pain_point": "",
                "feedback_to_student": "Good effort! Your explanation shows engagement with the material. Keep building on this.",
                "concepts_missed": [],
                "what_they_got_right": "You provided a substantive explanation.",
            }

    # ── Override verdict with score (prevent LLM inconsistency) ─
    score = int(result.get("understanding_score", 5))
    score = max(0, min(10, score))

    # Score overrides LLM verdict if they disagree significantly
    if result.get("verdict") == "NOT_YET" and score >= 7:
        result["verdict"] = "MASTERED"
    elif result.get("verdict") == "MASTERED" and score < 5:
        result["verdict"] = "PARTIAL"
    elif result.get("verdict") == "PARTIAL" and score >= 8:
        result["verdict"] = "MASTERED"

    verdict = result["verdict"]
    pain_point = result.get("pain_point", "") if verdict != "MASTERED" else ""
    feedback = result.get("feedback_to_student", "")
    what_right = result.get("what_they_got_right", "")
    concepts_missed = result.get("concepts_missed", [])

    return _build_result(
        verdict=verdict,
        score=score,
        pain_point=pain_point,
        feedback=feedback,
        what_right=what_right,
        concepts_missed=concepts_missed,
        prior_mastery=prior_mastery,
        attempt_number=attempt_number,
    )


def _build_result(
    verdict: str,
    score: int,
    pain_point: str,
    feedback: str,
    what_right: str,
    concepts_missed: list,
    prior_mastery: float,
    attempt_number: int,
) -> dict:
    """Build unified result dict with all fields both old and new code expects."""
    # Mastery update
    if verdict == "MASTERED":
        new_mastery = min(1.0, prior_mastery + 0.25)
    elif verdict == "PARTIAL":
        new_mastery = min(1.0, prior_mastery + 0.08)
    else:
        new_mastery = max(0.0, prior_mastery - 0.02)

    next_strategy_map = {1: "direct", 2: "analogy", 3: "example", 4: "decompose"}
    next_attempt = attempt_number + 1
    next_strategy = next_strategy_map.get(next_attempt, "decompose")

    # Normalised 0-1 scores for legacy compat
    norm = score / 10.0
    scores = {
        "core_idea": round(norm, 2),
        "reasoning_quality": round(norm * 0.9, 2),
        "own_words": round(norm * 0.85, 2),
        "edge_awareness": round(norm * 0.7, 2),
    }

    return {
        # New fields
        "verdict": verdict,
        "understanding_score": score,
        "pain_point": pain_point,
        "feedback_to_student": feedback,
        "what_they_got_right": what_right,
        "concepts_missed": concepts_missed,
        # Legacy compat fields
        "last_verdict": verdict,
        "scores": scores,
        "overall_score": round(norm, 3),
        "mastery_probability": round(new_mastery, 3),
        "advance": verdict == "MASTERED",
        "next_strategy": next_strategy,
        "needs_real_explanation": False,
        # For LangGraph state
        "should_advance": verdict == "MASTERED",
        "should_flag": next_attempt >= 5 and verdict != "MASTERED",
        "mastery_score": round(new_mastery, 3),
    }
