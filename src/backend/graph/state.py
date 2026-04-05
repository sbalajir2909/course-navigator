"""
graph/state.py
TypedDict definition for the LangGraph teaching loop state.
"""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class TeachingState(TypedDict):
    """
    Shared state threaded through the LangGraph teaching loop.

    Fields:
        module_id:            UUID string of the module being taught.
        student_id:           UUID string of the student.
        source_chunks:        List of raw text strings from the module's source material.
        student_history:      List of prior kc_attempt dicts for this student/module.
        current_explanation:  The teaching agent's most recent explanation string.
        student_response:     The student's latest explain-back text.
        validator_result:     The validator agent's latest result dict.
        mastery_probability:  Current BKT mastery probability (0.0–1.0).
        attempt_count:        Number of explain-back attempts so far.
        strategy:             Current teaching strategy key.
        should_advance:       Whether the student has met the mastery threshold.
    """

    module_id: str
    student_id: str
    source_chunks: list[str]
    student_history: list[dict[str, Any]]
    current_explanation: Optional[str]
    student_response: Optional[str]
    validator_result: Optional[dict[str, Any]]
    mastery_probability: float
    attempt_count: int
    strategy: str
    should_advance: bool
