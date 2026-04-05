"""
agents/teaching_agent.py
Strategy-aware Socratic teaching agent using GPT-4o-mini.
Strict forbidden-phrase check ensures clean, confident explanations.
"""
from __future__ import annotations
import os
from openai import AsyncOpenAI

TEACHING_SYSTEM_PROMPT = """You are a clear, confident Socratic tutor.

YOUR ONLY JOB: Explain the concept below simply and clearly, then ask the student to explain it back.

STRICT RULES — violating any of these makes you useless:
1. Teach ONLY what is in the SOURCE MATERIAL. Do not add external knowledge.
2. NEVER mention what the source material does NOT cover. Never say "the source doesn't address..." or "the material doesn't explain..." — this confuses students and teaches them nothing.
3. Keep your explanation to 4-6 sentences maximum. No walls of text.
4. Use simple, direct language. No hedging. No qualifiers. Teach confidently.
5. End EVERY explanation with ONE clear question: "Now explain [specific concept] back to me in your own words."
6. On attempt 2: use a concrete real-world analogy. Map it explicitly back to the concept.
7. On attempt 3: give one specific worked example. Show the concept in action.
8. On attempt 4: break it into 3 numbered steps. Simple. Sequential. Clear.

NEVER DO THESE:
- Never say "According to the source material..."
- Never say "The material doesn't address..."
- Never say "The source doesn't explicitly..."
- Never say "the source material does not"
- Never say "doesn't provide further details"
- Never say "not explicitly mentioned"
- Never say "not provided in the source"
- Never ask multiple questions
- Never write more than 6 sentences
- Never use the phrase "it is worth noting"
- Never hedge with "however" or "but" when describing the core concept"""

FORBIDDEN_PHRASES = [
    "source material does not",
    "material doesn't address",
    "source doesn't explicitly",
    "not explicitly mentioned",
    "not provided in the source",
    "doesn't provide further details",
    "the material doesn't",
    "the source doesn't",
    "according to the source",
    "the source material",
    "material does not",
    "doesn't address that",
]

STRATEGY_INSTRUCTIONS = {
    1: "Explain directly and clearly from the source material.",
    2: "Use a concrete real-world analogy. Map each part of the analogy explicitly back to the concept.",
    3: "Give one specific worked example. Show the concept applied step-by-step to a real scenario.",
    4: "Break it into exactly 3 numbered steps. One sentence each. Simple and sequential.",
}


async def teach_concept(
    module: dict,
    student_history: list,
    source_chunks: list[str],
    strategy: str = "direct",
    pain_point: str = "",
    attempt_number: int = 1,
    memory_context: str = "",
) -> str:
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Map strategy string to attempt number for instruction lookup
    strategy_to_attempt = {"direct": 1, "analogy": 2, "example": 3, "decompose": 4}
    effective_attempt = strategy_to_attempt.get(strategy, attempt_number)
    strategy_instruction = STRATEGY_INSTRUCTIONS.get(effective_attempt, STRATEGY_INSTRUCTIONS[4])

    # Build source context — MAX 150 words per chunk, 3 chunks max
    truncated_chunks = []
    for chunk in source_chunks[:3]:
        words = chunk.split()
        truncated_chunks.append(" ".join(words[:150]))
    source_context = "\n---\n".join(truncated_chunks) if truncated_chunks else module.get("description", "")

    objectives = ", ".join(module.get("learning_objectives", [])[:3])

    # Pain point context for reteaching
    pain_context = ""
    if pain_point and attempt_number > 1:
        pain_context = f"\nThe student's previous attempt struggled with: {pain_point}\nAddress this directly using the strategy above.\n"

    user_message = f"""SOURCE MATERIAL:
{source_context}

LEARNING OBJECTIVE: {objectives}
{pain_context}
STRATEGY FOR THIS ATTEMPT (#{attempt_number}): {strategy_instruction}

Explain the concept now. Maximum 6 sentences. End with your question."""

    # Build message history — last 2 turns only
    history = []
    for h in student_history[-2:]:
        exp = h.get("student_explanation", "")
        if exp and len(exp.split()) >= 5:
            history.append({"role": "user", "content": f"Student said: {exp[:200]}"})

    messages = [
        {"role": "system", "content": TEACHING_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    # Token guard
    total_chars = sum(len(m["content"]) for m in messages)
    if total_chars > 8000:
        messages = [messages[0], messages[-1]]

    # Primary: Groq (free). Fallback: GPT-4o-mini.
    try:
        from groq import Groq as _Groq
        _gclient = _Groq(api_key=os.getenv("GROQ_API_KEY"))
        _gr = _gclient.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=250,
            temperature=0.4,
        )
        explanation = _gr.choices[0].message.content.strip()
    except Exception:
        # Fallback to GPT-4o-mini
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=250,
                temperature=0.4,
            )
            explanation = response.choices[0].message.content.strip()
        except Exception:
            explanation = f"Let me explain {module.get('title', 'this concept')} differently. {module.get('description', '')} What part would you like me to clarify?"

    # Forbidden phrase check — regenerate once if triggered
    has_forbidden = any(phrase.lower() in explanation.lower() for phrase in FORBIDDEN_PHRASES)
    if has_forbidden:
        messages[-1]["content"] += "\n\nCRITICAL: Do NOT mention what the source doesn't cover. Only teach what IS there. No hedging. Be confident."
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=250,
                temperature=0.2,
            )
            explanation = response.choices[0].message.content.strip()
        except Exception:
            pass

    return explanation
