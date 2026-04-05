"""
agents/teaching_agent.py
Concept-aware Socratic teaching agent with adaptive strategy selection.

A module has multiple concepts. The agent teaches ONE concept at a time.
The concept's learning_objective drives the teaching and validation focus.

Strategies adapt based on student confusion signals and accumulated pain points —
not just attempt number. When a student says "I don't understand", the agent
CHANGES its approach rather than repeating the same explanation.
"""
from __future__ import annotations
import os
import re

TEACHING_SYSTEM_PROMPT = """You are a clear, confident Socratic tutor.

YOUR ONLY JOB: Explain ONE specific concept clearly and thoroughly, then ask the student to explain it back.

STRICT RULES:
1. Teach ONLY the specific concept listed below. Do not cover other concepts in this module.
2. Use ONLY information from the SOURCE MATERIAL. Do not add outside knowledge.
3. NEVER mention what the source material does NOT cover. Only teach what IS there.
4. Use simple, direct language. Teach confidently. No hedging.
5. End with ONE clear question: "Now explain [specific concept] back to me in your own words."
6. On attempt 2: use a concrete real-world analogy that maps back to the concept.
7. On attempt 3: give one specific worked example step-by-step.
8. On attempt 4: break into 3 numbered points. One sentence each.
9. If the source material includes [Page N] or [Slide N] markers, end your explanation with a brief citation on its own line: "Ref: Page N" or "Ref: Slide N". Use the page/slide number closest to where the concept appears in the source.

NEVER:
- Say "According to the source material..." or "The source doesn't address..."
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

# Each strategy gets a distinct instruction so the LLM cannot give the same explanation twice.
STRATEGY_INSTRUCTIONS = {
    "direct": (
        "Explain the concept directly and clearly from the source material. "
        "Lead with the core definition, then one supporting detail."
    ),
    "analogy": (
        "Use ONE concrete real-world analogy the student knows well (cooking, sports, everyday objects). "
        "Map EACH part of the analogy explicitly back to the concept. "
        "Do NOT repeat the direct explanation from the previous attempt."
    ),
    "example": (
        "Give ONE specific worked example — walk through it step by step. "
        "Show the concept in action. Do NOT use an analogy; use a concrete scenario. "
        "Do NOT repeat the direct explanation or analogy from previous attempts."
    ),
    "decompose": (
        "Break the concept into exactly 3 numbered sub-parts. One clear sentence each. "
        "Use the simplest possible words. Avoid any jargon. "
        "Do NOT repeat previous explanations — this is a full restructure."
    ),
    "simpler": (
        "The student is confused. Restart from scratch with the absolute simplest possible language. "
        "Imagine explaining to someone who has never heard of this topic. "
        "Use short sentences. No technical terms unless absolutely necessary — define each one. "
        "Do NOT reference or repeat any previous explanation."
    ),
    "visual": (
        "Describe the concept as if drawing a diagram or a simple flowchart in words. "
        "Use spatial language: 'imagine a box', 'on the left is X', 'an arrow points to Y'. "
        "Make the structure of the concept visible through language."
    ),
    "contrast": (
        "Explain the concept by contrasting it with what it is NOT. "
        "Start with a common misconception or wrong idea, then correct it. "
        "This helps the student understand boundaries of the concept."
    ),
    # Legacy integer keys for backward compat
    1: "Explain directly and clearly from the source material.",
    2: "Use one concrete real-world analogy. Map each part explicitly back to the concept.",
    3: "Give one specific worked example. Show the concept applied step-by-step.",
    4: "Break into exactly 3 numbered steps. One clear sentence each.",
}

# Strategy progression when student explicitly says "I don't understand"
# These are dramatically different from each other on purpose
CONFUSION_STRATEGY_SEQUENCE = ["simpler", "decompose", "visual", "contrast", "analogy", "example"]

# Default attempt-number-based progression
ATTEMPT_STRATEGY_MAP = {1: "direct", 2: "analogy", 3: "example", 4: "decompose", 5: "simpler"}


def _extract_page_refs(source_chunks: list[str]) -> str:
    """Extract [Page N] / [Slide N] markers from source chunks for citation."""
    refs: set[str] = set()
    for chunk in source_chunks:
        for match in re.finditer(r'\[(Page|Slide)\s+(\d+)\]', chunk, re.IGNORECASE):
            refs.add(f"{match.group(1).capitalize()} {match.group(2)}")
    if not refs:
        return ""
    sorted_refs = sorted(refs, key=lambda x: int(x.split()[-1]))
    return ", ".join(sorted_refs)


def select_adaptive_strategy(
    attempt_number: int,
    strategies_used: list[str],
    explicit_confusion: bool,
    pain_points: list[str],
) -> str:
    """
    Select the next strategy so it is never the same as one already used.
    If explicit confusion detected, use the confusion-specific sequence.
    """
    if explicit_confusion:
        # Pick first strategy from confusion sequence not yet used
        for s in CONFUSION_STRATEGY_SEQUENCE:
            if s not in strategies_used:
                return s
        return "simpler"  # fallback: always go simpler

    # Normal attempt-based progression — but skip already-used strategies
    default = ATTEMPT_STRATEGY_MAP.get(attempt_number, "decompose")
    if default not in strategies_used:
        return default

    # Fallback: pick any unused strategy
    all_strategies = ["direct", "analogy", "example", "decompose", "simpler", "visual", "contrast"]
    for s in all_strategies:
        if s not in strategies_used:
            return s
    return "simpler"


async def teach_concept(
    module: dict,
    student_history: list,
    source_chunks: list[str],
    strategy: str = "direct",
    pain_point: str = "",
    attempt_number: int = 1,
    memory_context: str = "",
    concept_index: int = 0,
    strategies_used: list[str] | None = None,
    explicit_confusion: bool = False,
    pain_points: list[str] | None = None,
) -> str:
    """
    Teach ONE concept from the module's concepts list.
    Adapts strategy based on student confusion and accumulated pain points.
    Falls back to full module teaching if no concepts defined.
    """
    from api.cf_client import complete as cf_complete

    if strategies_used is None:
        strategies_used = []
    if pain_points is None:
        pain_points = []

    # Select adaptive strategy if not explicitly provided or if re-using same one
    if strategy in strategies_used and attempt_number > 1:
        strategy = select_adaptive_strategy(
            attempt_number, strategies_used, explicit_confusion, pain_points
        )

    # Get the specific concept to teach
    concepts = module.get("concepts", [])
    if concepts and concept_index < len(concepts):
        current_concept = concepts[concept_index]
        concept_title = current_concept.get("title", module.get("title", ""))
        learning_objective = current_concept.get("learning_objective", "")
        key_points = current_concept.get("key_points", [])
    else:
        concept_title = module.get("title", "")
        learning_objective = ", ".join(module.get("learning_objectives", [])[:2])
        key_points = []

    # Build source context — max 200 words per chunk, 5 chunks
    source_text = "\n---\n".join(
        " ".join(c.split()[:200]) for c in source_chunks[:5]
    ) if source_chunks else module.get("description", "")

    # Extract page/slide references for citation
    page_refs = _extract_page_refs(source_chunks[:5])

    # Get strategy instruction
    strategy_key = strategy if strategy in STRATEGY_INSTRUCTIONS else attempt_number
    strategy_instruction = STRATEGY_INSTRUCTIONS.get(strategy_key, STRATEGY_INSTRUCTIONS["direct"])

    # Build pain point context — include all accumulated pain points, not just latest
    pain_context = ""
    if attempt_number > 1:
        if pain_points:
            # Show all distinct pain points so the agent doesn't repeat explanations that didn't work
            unique_pains = list(dict.fromkeys(p for p in pain_points if p))
            pain_context = f"\nThe student has struggled with: {'; '.join(unique_pains[-3:])}\nYou MUST address these gaps directly with your new approach.\n"
        elif pain_point:
            pain_context = f"\nThe student struggled with: {pain_point}\nAddress this directly.\n"

    if explicit_confusion:
        pain_context += "\nIMPORTANT: The student explicitly said they do not understand. DO NOT repeat or rephrase your previous explanation. Use a completely different approach.\n"

    # What strategies were already tried (so LLM knows what NOT to do)
    if strategies_used:
        pain_context += f"\nStrategies already tried (DO NOT repeat these): {', '.join(strategies_used)}\n"

    # Key points hint (if available)
    key_hints = ""
    if key_points:
        key_hints = f"\nKey points to cover: {', '.join(key_points[:5])}\n"

    # Page reference hint
    page_ref_hint = f"\nSource location: {page_refs}\n" if page_refs else ""

    user_message = f"""CONCEPT TO TEACH: {concept_title}
LEARNING OBJECTIVE: {learning_objective}
{key_hints}{page_ref_hint}
SOURCE MATERIAL:
{source_text}
{pain_context}
STRATEGY FOR ATTEMPT #{attempt_number}: {strategy_instruction}

Explain ONLY this specific concept thoroughly. End with your question. Include a "Ref: Page/Slide N" citation if source location is provided above."""

    # Build history context — keep last 6 turns (increased from 2) so the agent
    # can see the full trajectory of what hasn't worked yet
    history = []
    for h in student_history[-6:]:
        exp = h.get("student_explanation", "")
        verdict = h.get("verdict", "")
        if exp and len(exp.split()) >= 3:
            history.append({
                "role": "user",
                "content": f"[Attempt {h.get('attempt_number', '?')} — {verdict}] Student said: {exp[:200]}"
            })

    messages = [
        {"role": "system", "content": TEACHING_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    # Token guard — increased to 12000 chars to accommodate longer history
    if sum(len(m["content"]) for m in messages) > 12000:
        # Keep system + last 3 history turns + current
        messages = [messages[0]] + messages[-4:]

    temp = 0.5 if attempt_number > 2 else 0.4
    # cf_complete already handles CF → OpenAI fallback internally
    try:
        explanation = await cf_complete(messages, model_key="teach", max_tokens=500, temperature=temp)
    except Exception:
        explanation = (
            f"Let me try explaining {concept_title} differently. "
            f"{module.get('description', 'This is an important concept worth understanding carefully.')} "
            f"The key idea is to understand the core principles and how they apply. "
            f"Think step by step about what you already know. "
            f"Now — can you explain {concept_title} back to me in your own words?"
        )

    # Forbidden phrase check — regenerate once with a stricter prompt
    if any(p.lower() in explanation.lower() for p in FORBIDDEN_PHRASES):
        messages[-1]["content"] += "\n\nCRITICAL: Only teach what IS in the source. Never mention gaps."
        try:
            explanation = await cf_complete(messages, model_key="teach", max_tokens=300, temperature=0.2)
        except Exception:
            pass

    return explanation


async def generate_prereq_drill(
    pain_point: str,
    concept_title: str,
    source_chunks: list[str],
    module_title: str = "",
) -> tuple[str, str]:
    """
    Given a specific knowledge gap (pain_point), generate:
      - gap_name: a short label for the missing foundational idea
      - micro_lesson: 3-5 sentence first-principles explanation of just that gap,
        ending with a question asking the student to explain it back

    This is used to drill prerequisite understanding inline before resuming
    the main concept.
    """
    from api.cf_client import complete_json as cf_json_func

    source_text = "\n---\n".join(
        " ".join(c.split()[:100]) for c in source_chunks[:3]
    ) if source_chunks else ""

    prompt = f"""A student is learning "{concept_title}" from a module on "{module_title}".
After two failed attempts they still cannot explain it. Their specific gap is:

PAIN POINT: {pain_point}

Your job: identify the ONE foundational concept that, if the student understood it,
would unlock their understanding of "{concept_title}". Then write a short micro-lesson
explaining just that foundational concept from first principles.

Source material (for context):
{source_text[:400]}

Rules for the micro-lesson:
- 3-5 sentences maximum
- Explain from FIRST PRINCIPLES — build it up from what anyone would know
- DO NOT mention "{concept_title}" — teach only the foundational gap
- End with: "Now explain [gap concept] back to me in your own words."
- Use simple, concrete language — no jargon without definition

Return ONLY valid JSON:
{{
  "gap_name": "Short name for the foundational gap (5-8 words max)",
  "micro_lesson": "3-5 sentence explanation ending with a question"
}}"""

    try:
        data = await cf_json_func(
            messages=[{"role": "user", "content": prompt}],
            model_key="teach",
            max_tokens=300,
            temperature=0.35,
        )
        gap_name    = data.get("gap_name", f"foundational concept behind {concept_title}")
        micro_lesson = data.get("micro_lesson", "")
        if not micro_lesson:
            raise ValueError("empty micro_lesson")
        return gap_name, micro_lesson
    except Exception as e:
        print(f"[PREREQ_DRILL] Generation failed: {e} — using fallback")
        gap_name = f"core idea behind {concept_title}"
        micro_lesson = (
            f"Before we continue with {concept_title}, let's make sure we have the foundation. "
            f"{pain_point.capitalize() if pain_point else 'There seems to be a gap in the underlying concept.'}. "
            f"Think of it this way: every complex idea is built on simpler ones. "
            f"The key building block here is understanding why this matters in context. "
            f"Now explain this foundational idea back to me in your own words."
        )
        return gap_name, micro_lesson
