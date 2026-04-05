"""
agents/teaching_agent.py
Strategy-aware Socratic teaching agent.
Switches strategy based on attempt_number and directly addresses prior pain_point.
"""
from __future__ import annotations
import os
from groq import Groq

STRATEGY_PROMPTS = {
    "direct": """Teach this concept directly from the source material.
Structure: (1) One-sentence definition. (2) Why it matters. (3) Key components or steps. (4) Ask student to explain back.
Keep it focused. 3-4 paragraphs max.""",

    "analogy": """The student struggled on their first attempt. Use a concrete real-world analogy.
Structure: (1) Pick ONE familiar analogy that maps directly to the concept. (2) Map each part of the analogy to the actual concept. (3) Explain what the analogy does NOT capture. (4) Ask student to extend the analogy themselves.
The analogy must be specific — not "it's like a car" but "it's like the dashboard warning lights in a car, where each light = one layer of the framework."
3-4 paragraphs max.""",

    "example": """The student is still struggling. Walk through ONE concrete worked example.
Structure: (1) Set up a specific real scenario by name. (2) Apply the concept step-by-step to that scenario. (3) Show what would happen WITHOUT this concept. (4) Ask student to apply the concept to a different scenario.
Be specific — use names, numbers, and concrete details. 3-4 paragraphs max.""",

    "decompose": """The student is significantly struggling. Break the concept into its smallest parts.
Structure: (1) Identify the 3-4 atomic sub-concepts that make up this topic. (2) Explain each sub-concept in one sentence. (3) Show how they connect. (4) Ask student to explain just ONE sub-concept first.
Do not teach the whole concept at once. Build from pieces. 3-4 paragraphs max.""",
}

SYSTEM_RULES = """STRICT RULES — FOLLOW EXACTLY:
1. Use ONLY information from the source material. Do NOT add outside knowledge.
2. If the source doesn't cover something, say "The material doesn't address that specifically."
3. Maximum 4 paragraphs. No essays.
4. End with exactly ONE specific question asking the student to explain back.
5. Do NOT repeat what was already explained if there's prior attempt history.
6. Do NOT use filler phrases like "Great question!" or "Absolutely!"
7. Be direct and specific."""

async def teach_concept(
    module: dict,
    student_history: list,
    source_chunks: list[str],
    strategy: str = "direct",
    pain_point: str = "",
    attempt_number: int = 1,
    memory_context: str = "",
) -> str:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    source_text = "\n\n".join(chunk[:400] for chunk in source_chunks[:6]) if source_chunks else module.get("description", "No source material.")
    strategy_instruction = STRATEGY_PROMPTS.get(strategy, STRATEGY_PROMPTS["direct"])
    objectives = ", ".join(module.get("learning_objectives", [])[:3])

    # Build pain point context for reteaching
    pain_context = ""
    if pain_point and attempt_number > 1:
        pain_context = f"""
PREVIOUS ATTEMPT FEEDBACK:
The student struggled with: "{pain_point}"
You MUST directly address this in your explanation. Don't just re-explain — fix the specific gap identified above."""

    # Build attempt history (last 2 only)
    history_text = ""
    if student_history:
        recent = [h for h in student_history[-2:]
                  if h.get("student_explanation", "").lower().strip() not in
                  {"i understand", "i understand ✓", "i get it", "i don't know", "i dont know"}]
        if recent:
            parts = [f'Student said: "{h["student_explanation"][:150]}" '
                     f'(verdict: {h.get("verdict", "unknown")})' for h in recent]
            history_text = "\nPrevious attempts:\n" + "\n".join(parts)

    prompt = f"""{SYSTEM_RULES}

MODULE: {module.get("title", "Unknown")}
LEARNING OBJECTIVES: {objectives}

SOURCE MATERIAL (use ONLY this):
{source_text}
{history_text}
{pain_context}
{f"Student context: {memory_context}" if memory_context else ""}

STRATEGY FOR THIS ATTEMPT (attempt #{attempt_number}):
{strategy_instruction}

Teach now:"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,
        )
        return response.choices[0].message.content
    except Exception:
        return (f"Let me explain {module.get('title', 'this concept')} differently. "
                f"{module.get('description', '')} "
                f"Can you tell me what you already know about this topic?")
