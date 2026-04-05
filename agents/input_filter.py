"""
agents/input_filter.py
Pre-filter for student input — runs BEFORE any LLM call.
Pure string logic, microsecond execution.
Catches non-answers, trivial inputs, and off-topic submissions.
"""

NON_ANSWER_PHRASES = {
    "okay", "ok", "okay what next", "what next", "next", "i don't know",
    "i dont know", "idk", "not sure", "no idea", "skip", "pass", "help",
    "i give up", "move on", "continue", "got it", "understood", "yes",
    "no", "maybe", "sure", "alright", "fine", "okay next", "next please",
    "what's next", "whats next", "move to next", "go on", "proceed",
    "okay, what next?", "okay what next?", "what next?", "next?",
    "i understand", "i understand ✓", "i get it", "i know",
    "i understand this concept", "i understand this concept well",
    "let's move on", "lets move on", "can we move on",
    "i'm ready", "im ready", "ready", "done", "finished",
}


def filter_student_input(student_input: str) -> dict:
    """
    Returns:
    {
        "is_valid": bool,
        "rejection_reason": str | None,
        "rejection_type": "too_short" | "non_answer" | "question_only" | None
    }
    """
    text = student_input.strip()
    text_lower = text.lower().strip(".,!?")
    word_count = len(text.split())

    # Check 1: Empty
    if not text:
        return {
            "is_valid": False,
            "rejection_reason": "Please type your explanation before submitting.",
            "rejection_type": "too_short",
        }

    # Check 2: Too short (under 10 words)
    if word_count < 10:
        return {
            "is_valid": False,
            "rejection_reason": f"Your response is too short ({word_count} word{'s' if word_count != 1 else ''}). Please write at least 2-3 sentences explaining what you understood.",
            "rejection_type": "too_short",
        }

    # Check 3: Known non-answer phrases
    if text_lower in NON_ANSWER_PHRASES:
        return {
            "is_valid": False,
            "rejection_reason": "Please explain the concept in your own words — I need to see that you understood it. Even a rough explanation is fine.",
            "rejection_type": "non_answer",
        }

    # Check 4: Just a question (ends with ? and short)
    if text.endswith("?") and word_count < 20:
        return {
            "is_valid": False,
            "rejection_reason": "It looks like you asked a question. Please explain what you understand about the concept so far — you can ask questions after.",
            "rejection_type": "question_only",
        }

    # Check 5: Repeating "explain" or "what is" without substance
    if word_count < 15 and any(p in text_lower for p in ["what is", "how does", "explain", "can you"]):
        return {
            "is_valid": False,
            "rejection_reason": "Please explain the concept yourself rather than asking me to re-explain. Tell me what you understood.",
            "rejection_type": "non_answer",
        }

    return {"is_valid": True, "rejection_reason": None, "rejection_type": None}
