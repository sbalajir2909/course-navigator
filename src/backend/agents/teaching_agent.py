"""
agents/teaching_agent.py - Groq version with strict anti-hallucination rules.
Every teaching turn is grounded in source material only.
"""
from __future__ import annotations
import os
from groq import Groq

STRATEGIES = {
    "initial": "Teach this concept clearly. Start with a 1-sentence definition, then explain with ONE concrete example from the source material. End by asking the student to explain it back in their own words.",
    "simplified": "The student is struggling. Break this down into the simplest possible terms. Use a very short analogy (1-2 sentences). Focus only on the single most important concept. Ask them ONE specific question to check understanding.",
    "analogy": "Explain using a memorable real-world analogy. Map each key component of the concept to something familiar in everyday life. Make it visual. Then ask them to extend the analogy themselves.",
    "worked_example": "Walk through ONE concrete worked example step by step. Show your reasoning at each step. Be specific and use numbers/names where possible. Then ask the student to explain what happened at each step.",
}

SYSTEM_RULES = """STRICT TEACHING RULES — FOLLOW EXACTLY:
1. ONLY use information from the source material provided. Do NOT add outside knowledge.
2. If the source material doesn't cover something, say "The material doesn't cover that specifically."
3. Keep responses to 3-5 paragraphs maximum. Do NOT write essays.
4. End EVERY response with exactly ONE clear question asking the student to explain back.
5. Do NOT repeat yourself if the student has already seen an explanation — build on it.
6. Do NOT say "Great question!" or other filler phrases.
7. Be direct and specific. Vague explanations are worse than short ones."""

async def teach_concept(
    module: dict,
    student_history: list,
    source_chunks: list[str],
    strategy: str = "initial",
    memory_context: str = ""
) -> str:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    # Limit source text strictly to avoid token overflow
    source_text = "\n\n".join(chunk[:400] for chunk in source_chunks[:6]) if source_chunks else module.get("description", "No source material available.")
    
    strategy_instruction = STRATEGIES.get(strategy, STRATEGIES["initial"])

    # Build history context (last 2 attempts only to save tokens)
    history_text = ""
    if student_history:
        recent = student_history[-2:]
        history_parts = []
        for h in recent:
            exp = h.get("student_explanation", "")
            score = h.get("mastery_probability", 0)
            if exp and exp.lower().strip() not in ["i understand", "i understand ✓", "i get it"]:
                history_parts.append(f"Student said: \"{exp[:200]}\" (mastery: {round(score*100)}%)")
        if history_parts:
            history_text = "\nPrevious attempts:\n" + "\n".join(history_parts)

    prompt = f"""{SYSTEM_RULES}

Module: {module.get('title', 'Unknown')}
Learning Objectives: {', '.join(module.get('learning_objectives', [])[:3])}

SOURCE MATERIAL (use ONLY this):
{source_text}
{history_text}
{f"Student memory: {memory_context}" if memory_context else ""}

Teaching strategy: {strategy_instruction}

Teach the concept now:"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,  # Hard limit — no essays
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"I'm having trouble connecting right now. The module covers: {module.get('description', 'this topic')}. Can you tell me what you already know about it?"
