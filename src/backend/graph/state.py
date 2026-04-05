"""
graph/state.py
TeachingState — full state for the LangGraph teaching loop.
"""
from __future__ import annotations
from typing import Any, TypedDict


class TeachingState(TypedDict, total=False):
    # Session identity
    session_id: str
    student_id: str
    module_id: str

    # Module + source material
    module: dict[str, Any]          # full module dict with title, objectives, etc.
    source_chunks: list[str]        # raw text chunks from source material

    # Teaching state
    attempt_number: int             # starts at 1, increments after each PARTIAL/NOT_YET
    teaching_strategy: str          # "direct" | "analogy" | "example" | "decompose"
    current_explanation: str        # what the AI just taught

    # Student response
    student_response: str           # latest explain-back text

    # Validator output
    last_verdict: str               # "MASTERED" | "PARTIAL" | "NOT_YET"
    pain_point: str                 # from latest validation
    pain_points: list[str]          # accumulated across all attempts
    concepts_missed: list[str]      # from latest validator output
    feedback_to_student: str        # targeted feedback message

    # Mastery tracking
    mastery_probability: float      # BKT probability
    scores: dict[str, float]        # dimension scores from validator

    # History
    student_history: list[dict[str, Any]]  # all prior attempts

    # Prerequisite recommendations
    prerequisite_modules: list[dict[str, Any]]

    # Routing
    should_advance: bool
    should_flag: bool
