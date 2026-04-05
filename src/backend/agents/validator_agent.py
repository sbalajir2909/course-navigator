"""
agents/validator_agent.py
Reference-Anchored Semantic Validator using GPT-4o.

Architecture:
1. Pre-filter catches non-answers (no LLM call) — in input_filter.py
2. Generate or retrieve reference answer for this module
3. Compare student explanation to reference semantically
4. Single understanding_score (0-10), not multi-dimensional rubric
5. Score-based reconciliation — score overrides verdict if they disagree
"""
from __future__ import annotations
import os, json
from openai import AsyncOpenAI
from api.db import supabase_query

# Initial mastery is 0 — not 0.3
P_INIT = 0.0

# In-memory reference cache: module_id -> reference text
_reference_cache: dict[str, str] = {}

VALIDATOR_SYSTEM_PROMPT = """You are an expert educator evaluating whether a student understood a concept.

YOUR JOB: Determine if the student understood the CORE IDEA. You are NOT looking for gaps.

EVALUATION PHILOSOPHY:
- A student who explains the core concept correctly in simple terms has understood it.
- Correct technical vocabulary used correctly = evidence of understanding, NOT copying.
- Students should only be evaluated on what they were taught, not on external knowledge.
- Different words conveying the same correct meaning = full credit.
- Partial understanding = partial credit. Not zero credit.

SCORING (0-10):
- 8-10: Student clearly understood the core concept → MASTERED
- 5-7: Student got the main idea but missed some nuance → PARTIAL
- 0-4: Student fundamentally misunderstood or barely engaged → NOT_YET

WHAT YOU ARE COMPARING:
You receive a REFERENCE ANSWER — what a correct student explanation looks like.
Ask: "Does this student's explanation convey the same core meaning as the reference?"
If yes → MASTERED. If mostly → PARTIAL. If no → NOT_YET.

DO NOT penalize for:
- Using correct technical terms from the source material
- Different sentence structure or word order
- Shorter explanations that still capture the core idea
- Not mentioning things the reference mentions if they demonstrated core understanding

DO penalize for:
- Getting the core concept factually wrong
- Describing a completely different concept
- Vague platitudes with no specific content

Return ONLY valid JSON. No markdown. No explanation outside the JSON."""


async def _get_or_generate_reference(
    module_id: str,
    module: dict,
    source_chunks: list[str],
) -> str:
    """Get reference explanation from cache/DB, or generate and cache."""
    if module_id and module_id in _reference_cache:
        return _reference_cache[module_id]

    # Check DB
    if module_id:
        try:
            rows = await supabase_query(
                "module_references",
                params={"module_id": f"eq.{module_id}", "select": "reference_explanation"},
            )
            if rows and rows[0].get("reference_explanation"):
                ref = rows[0]["reference_explanation"]
                _reference_cache[module_id] = ref
                return ref
        except Exception:
            pass

    # Generate with GPT-4o-mini
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    module_content = "\n\n".join(chunk[:400] for chunk in source_chunks[:3]) if source_chunks else module.get("description", "")
    objectives = ", ".join(module.get("learning_objectives", [])[:3])
    title = module.get("title", "this concept")

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Write a model student explanation — 3-4 sentences, simple language. Write as if a student is explaining to a peer, not as a textbook. Do NOT mention what the source doesn't cover."},
                {"role": "user", "content": f"Source material: {module_content[:800]}\nLearning objective: {objectives}\nModule: {title}\n\nWrite what a correct student explanation looks like. 3-4 sentences. Show core concept + why it matters + one concrete implication."},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        reference = response.choices[0].message.content.strip()
    except Exception:
        reference = f"A correct explanation of {title} would cover: {objectives}"

    if module_id:
        _reference_cache[module_id] = reference
        try:
            await supabase_query(
                "module_references",
                method="POST",
                json={"module_id": module_id, "reference_explanation": reference},
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
    """Main validation. Returns complete result dict."""
    module_id = module.get("id", module.get("module_id", ""))
    module_title = module.get("title", "this concept")
    objectives = ", ".join(module.get("learning_objectives", [])[:3])

    # Get reference answer
    reference = await _get_or_generate_reference(module_id, module, source_chunks)

    # Truncate agent explanation to max 150 words
    agent_words = agent_explanation.split()[:150] if agent_explanation else []
    agent_truncated = " ".join(agent_words) if agent_words else "(not available)"

    prompt = f"""CONCEPT: {module_title}
LEARNING OBJECTIVE: {objectives}

WHAT CORRECT UNDERSTANDING LOOKS LIKE (reference answer):
{reference}

WHAT THE TEACHING AGENT EXPLAINED TO THE STUDENT:
{agent_truncated}

STUDENT'S EXPLANATION (attempt {attempt_number} of 5):
{student_explanation}

Evaluate: Does the student's explanation convey the same core meaning as the reference answer?

Return JSON:
{{
  "understanding_score": <0-10>,
  "verdict": "MASTERED" | "PARTIAL" | "NOT_YET",
  "what_they_got_right": "<one sentence: what they understood correctly. NEVER empty — always find something positive.>",
  "pain_point": "<If PARTIAL/NOT_YET: one precise sentence about the specific gap. If MASTERED: empty string.>",
  "feedback_to_student": "<Two sentences. Start with what they got right. Then specific guidance if needed. Never say 'Good effort' generically.>",
  "concepts_missed": ["<only concepts in the reference that were clearly absent from student explanation>"]
}}"""

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=350,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
    except Exception:
        # Fallback to Groq
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
                max_tokens=350,
            )
            result = json.loads(gr.choices[0].message.content)
        except Exception:
            # Last resort: give partial credit for substantive responses
            result = {
                "understanding_score": 5,
                "verdict": "PARTIAL",
                "what_they_got_right": "You provided a substantive explanation showing engagement with the material.",
                "pain_point": "Could not fully evaluate — please try again.",
                "feedback_to_student": "Your explanation showed effort. Please try submitting again for a full evaluation.",
                "concepts_missed": [],
            }

    # Score-based reconciliation — trust score over label
    score = max(0, min(10, int(result.get("understanding_score", 5))))

    if score >= 8:
        result["verdict"] = "MASTERED"
    elif score >= 5:
        if result.get("verdict") == "MASTERED":
            result["verdict"] = "PARTIAL"
        elif result.get("verdict") == "NOT_YET":
            result["verdict"] = "PARTIAL"
    else:
        if result.get("verdict") == "MASTERED":
            result["verdict"] = "PARTIAL"

    verdict = result["verdict"]

    # Clean up fields
    if verdict == "MASTERED":
        result["pain_point"] = ""
        result["concepts_missed"] = []

    if not result.get("what_they_got_right"):
        result["what_they_got_right"] = "You engaged with the concept and made a genuine attempt to explain it."

    return _build_result(
        verdict=verdict,
        score=score,
        pain_point=result.get("pain_point", ""),
        feedback=result.get("feedback_to_student", ""),
        what_right=result.get("what_they_got_right", ""),
        concepts_missed=result.get("concepts_missed", []),
        prior_mastery=prior_mastery,
        attempt_number=attempt_number,
    )


def _build_result(
    verdict: str, score: int, pain_point: str, feedback: str,
    what_right: str, concepts_missed: list,
    prior_mastery: float, attempt_number: int,
) -> dict:
    """Build unified result dict."""
    if verdict == "MASTERED":
        new_mastery = min(1.0, prior_mastery + 0.25)
    elif verdict == "PARTIAL":
        new_mastery = min(1.0, prior_mastery + 0.08)
    else:
        new_mastery = max(0.0, prior_mastery - 0.02)

    strategy_map = {1: "direct", 2: "analogy", 3: "example", 4: "decompose"}
    next_attempt = attempt_number + 1
    next_strategy = strategy_map.get(next_attempt, "decompose")

    norm = score / 10.0
    scores = {
        "core_idea": round(norm, 2),
        "reasoning_quality": round(norm * 0.9, 2),
        "own_words": round(norm * 0.85, 2),
        "edge_awareness": round(norm * 0.7, 2),
    }

    return {
        "verdict": verdict,
        "last_verdict": verdict,
        "understanding_score": score,
        "pain_point": pain_point,
        "feedback_to_student": feedback,
        "what_they_got_right": what_right,
        "concepts_missed": concepts_missed,
        "scores": scores,
        "overall_score": round(norm, 3),
        "mastery_probability": round(new_mastery, 3),
        "mastery_score": round(new_mastery, 3),
        "advance": verdict == "MASTERED",
        "next_strategy": next_strategy,
        "should_advance": verdict == "MASTERED",
        "should_flag": next_attempt >= 5 and verdict != "MASTERED",
        "needs_real_explanation": False,
    }
