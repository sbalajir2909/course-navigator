"""
agents/teaching_agent.py
Concept-aware Socratic teaching agent.

A module has multiple concepts. The agent teaches ONE concept at a time.
The concept's learning_objective drives the teaching and validation focus.
"""
from __future__ import annotations
import os
from openai import AsyncOpenAI

TEACHING_SYSTEM_PROMPT = """You are a clear, confident Socratic tutor.

YOUR ONLY JOB: Explain ONE specific concept simply and clearly, then ask the student to explain it back.

STRICT RULES:
1. Teach ONLY the specific concept listed below. Do not cover other concepts in this module.
2. Use ONLY information from the SOURCE MATERIAL. Do not add outside knowledge.
3. NEVER mention what the source material does NOT cover. Only teach what IS there.
4. Keep your explanation to 4-6 sentences maximum.
5. Use simple, direct language. Teach confidently. No hedging.
6. End with ONE clear question: "Now explain [specific concept] back to me in your own words."
7. On attempt 2: use a concrete real-world analogy that maps back to the concept.
8. On attempt 3: give one specific worked example step-by-step.
9. On attempt 4: break into 3 numbered points. One sentence each.

NEVER:
- Say "According to the source material..." or "The source doesn't address..."
- Write more than 6 sentences
- Ask multiple questions
- Hedge or qualify the core concept"""

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
]

STRATEGY_INSTRUCTIONS = {
    "direct":    "Explain the concept directly and clearly from the source material.",
    "analogy":   "Use one concrete real-world analogy. Map each part explicitly back to the concept.",
    "example":   "Give one specific worked example. Show the concept applied step-by-step.",
    "decompose": "Break into exactly 3 numbered steps. One clear sentence each.",
    # Legacy names
    1: "Explain directly and clearly from the source material.",
    2: "Use one concrete real-world analogy. Map each part explicitly back to the concept.",
    3: "Give one specific worked example. Show the concept applied step-by-step.",
    4: "Break into exactly 3 numbered steps. One clear sentence each.",
}


async def teach_concept(
    module: dict,
    student_history: list,
    source_chunks: list[str],
    strategy: str = "direct",
    pain_point: str = "",
    attempt_number: int = 1,
    memory_context: str = "",
    # New: current concept index within the module
    concept_index: int = 0,
) -> str:
    """
    Teach ONE concept from the module's concepts list.
    If concept_index is valid, focus on that specific concept.
    Falls back to full module teaching if no concepts defined.
    """
    # Primary: Groq. Fallback: GPT-4o-mini.
    from groq import Groq as _Groq
    gclient = _Groq(api_key=os.getenv("GROQ_API_KEY"))

    # Get the specific concept to teach
    concepts = module.get("concepts", [])
    if concepts and concept_index < len(concepts):
        current_concept = concepts[concept_index]
        concept_title = current_concept.get("title", module.get("title", ""))
        learning_objective = current_concept.get("learning_objective", "")
        key_points = current_concept.get("key_points", [])
    else:
        # No concepts defined — teach the whole module (legacy)
        concept_title = module.get("title", "")
        learning_objective = ", ".join(module.get("learning_objectives", [])[:2])
        key_points = []

    # Build source context — max 150 words per chunk, 3 chunks
    source_text = "\n---\n".join(
        " ".join(c.split()[:150]) for c in source_chunks[:3]
    ) if source_chunks else module.get("description", "")

    # Get strategy instruction
    strategy_key = strategy if strategy in STRATEGY_INSTRUCTIONS else attempt_number
    strategy_instruction = STRATEGY_INSTRUCTIONS.get(strategy_key, STRATEGY_INSTRUCTIONS["direct"])

    # Pain point context
    pain_context = ""
    if pain_point and attempt_number > 1:
        pain_context = f"\nThe student struggled with: {pain_point}\nAddress this directly.\n"

    # Key points hint (if available)
    key_hints = ""
    if key_points:
        key_hints = f"\nKey points to cover: {', '.join(key_points[:3])}\n"

    user_message = f"""CONCEPT TO TEACH: {concept_title}
LEARNING OBJECTIVE: {learning_objective}
{key_hints}
SOURCE MATERIAL:
{source_text}
{pain_context}
STRATEGY FOR ATTEMPT #{attempt_number}: {strategy_instruction}

Explain ONLY this specific concept. Maximum 6 sentences. End with your question."""

    # Build minimal history (last 2 turns only)
    history = []
    for h in student_history[-2:]:
        exp = h.get("student_explanation", "")
        if exp and len(exp.split()) >= 5:
            history.append({"role": "user", "content": f"Student said: {exp[:150]}"})

    messages = [
        {"role": "system", "content": TEACHING_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    # Token guard
    if sum(len(m["content"]) for m in messages) > 6000:
        messages = [messages[0], messages[-1]]

    try:
        resp = gclient.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=250,
            temperature=0.4,
        )
        explanation = resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[TEACH] Groq failed: {e} — trying GPT-4o-mini")
        try:
            client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=250,
                temperature=0.4,
            )
            explanation = response.choices[0].message.content.strip()
        except Exception:
            explanation = f"Let me explain {concept_title}. {module.get('description', '')} What do you already know about this?"

    # Forbidden phrase check — regenerate once if triggered
    if any(p.lower() in explanation.lower() for p in FORBIDDEN_PHRASES):
        messages[-1]["content"] += "\n\nCRITICAL: Only teach what IS in the source. Never mention gaps or what the source doesn't cover."
        try:
            resp2 = gclient.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=250,
                temperature=0.2,
            )
            explanation = resp2.choices[0].message.content.strip()
        except Exception:
            pass

    return explanation
