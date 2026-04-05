"""
agents/grading_agent.py
Dedicated grading agent — evaluates if what the student explained is factually correct
by comparing against the source material. Separate from the validator (which scores effort/format).

This is the "did they actually learn it?" check.
"""
from __future__ import annotations
import json


async def grade_explanation(
    student_explanation: str,
    module: dict,
    source_chunks: list[str],
) -> dict:
    """
    Grade a student's explanation against source material.
    
    Returns:
        {
            "correct_points": ["point1 they got right", ...],
            "incorrect_points": ["misconception1", ...],
            "missing_points": ["key concept they didn't mention", ...],
            "accuracy_score": 0.0-1.0,
            "completeness_score": 0.0-1.0,
            "grade_letter": "A" | "B" | "C" | "D" | "F",
            "learning_verdict": "solid" | "partial" | "weak" | "incorrect",
            "detailed_feedback": "..."
        }
    """
    from api.cf_client import complete_json as cf_json
    source_text = "\n\n".join(chunk[:500] for chunk in source_chunks[:5]) if source_chunks else ""
    
    objectives = module.get("learning_objectives", [])
    objectives_text = "\n".join(f"- {obj}" for obj in objectives[:5])
    
    prompt = f"""You are a strict but fair grading professor. Compare the student's explanation against the source material and learning objectives.

MODULE: {module.get('title', 'Unknown')}

LEARNING OBJECTIVES (what the student SHOULD know after this module):
{objectives_text}

SOURCE MATERIAL (the ground truth — ONLY these facts are correct):
{source_text[:3000]}

STUDENT'S EXPLANATION:
"{student_explanation}"

GRADING RULES:
1. A point is CORRECT only if it matches the source material
2. A point is INCORRECT if it contradicts the source material or is fabricated
3. A point is MISSING if it's a key concept from the objectives that the student didn't mention
4. accuracy_score: what fraction of what they said is correct (0.0-1.0)
5. completeness_score: what fraction of key concepts they covered (0.0-1.0)
6. Be STRICT — do not give credit for vague statements like "it's important" without specifics
7. grade_letter: A (90%+), B (75-89%), C (60-74%), D (40-59%), F (<40%)
8. learning_verdict: "solid" if they clearly understood, "partial" if they got the gist but missed key parts, "weak" if mostly vague/incomplete, "incorrect" if they have misconceptions

Return ONLY valid JSON:
{{
    "correct_points": [],
    "incorrect_points": [],
    "missing_points": [],
    "accuracy_score": 0.0,
    "completeness_score": 0.0,
    "grade_letter": "F",
    "learning_verdict": "weak",
    "detailed_feedback": "Specific feedback"
}}"""

    try:
        result = await cf_json(
            messages=[{"role": "user", "content": prompt}],
            model_key="validate",
            temperature=0.1,
            max_tokens=500,
        )
        
        # Ensure all expected fields exist
        result.setdefault("correct_points", [])
        result.setdefault("incorrect_points", [])
        result.setdefault("missing_points", [])
        result.setdefault("accuracy_score", 0.0)
        result.setdefault("completeness_score", 0.0)
        result.setdefault("grade_letter", "F")
        result.setdefault("learning_verdict", "weak")
        result.setdefault("detailed_feedback", "")
        
        # Clamp scores
        result["accuracy_score"] = max(0.0, min(1.0, float(result["accuracy_score"])))
        result["completeness_score"] = max(0.0, min(1.0, float(result["completeness_score"])))
        
        return result
    except Exception as e:
        return {
            "correct_points": [],
            "incorrect_points": [],
            "missing_points": ["Unable to grade — please try again"],
            "accuracy_score": 0.0,
            "completeness_score": 0.0,
            "grade_letter": "F",
            "learning_verdict": "weak",
            "detailed_feedback": f"Grading error: {str(e)[:100]}",
        }


def compute_learning_curve_score(grades: list[dict]) -> dict:
    """
    Given a list of grading results for a student across multiple modules,
    compute their learning curve — are they improving over time?
    
    Returns:
        {
            "trend": "improving" | "flat" | "declining",
            "avg_accuracy": float,
            "avg_completeness": float,
            "modules_solid": int,
            "modules_weak": int,
            "recommendation": str
        }
    """
    if not grades:
        return {
            "trend": "flat", "avg_accuracy": 0.0, "avg_completeness": 0.0,
            "modules_solid": 0, "modules_weak": 0,
            "recommendation": "No data yet"
        }
    
    accuracies = [g.get("accuracy_score", 0) for g in grades]
    completeness = [g.get("completeness_score", 0) for g in grades]
    verdicts = [g.get("learning_verdict", "weak") for g in grades]
    
    avg_acc = sum(accuracies) / len(accuracies)
    avg_comp = sum(completeness) / len(completeness)
    solid = sum(1 for v in verdicts if v == "solid")
    weak = sum(1 for v in verdicts if v in ("weak", "incorrect"))
    
    # Detect trend from last 3 grades
    if len(accuracies) >= 3:
        recent = accuracies[-3:]
        if recent[-1] > recent[0] + 0.1:
            trend = "improving"
        elif recent[-1] < recent[0] - 0.1:
            trend = "declining"
        else:
            trend = "flat"
    else:
        trend = "flat"
    
    # Generate recommendation
    if trend == "declining":
        rec = "Student's understanding is declining — consider revisiting earlier prerequisite modules."
    elif avg_acc < 0.4:
        rec = "Student has significant knowledge gaps. Recommend 1-on-1 review with instructor."
    elif avg_acc < 0.7:
        rec = "Student has partial understanding. Focus on missing concepts identified in grading."
    else:
        rec = "Student is progressing well. Ready for more advanced material."
    
    return {
        "trend": trend,
        "avg_accuracy": round(avg_acc, 2),
        "avg_completeness": round(avg_comp, 2),
        "modules_solid": solid,
        "modules_weak": weak,
        "recommendation": rec,
    }
