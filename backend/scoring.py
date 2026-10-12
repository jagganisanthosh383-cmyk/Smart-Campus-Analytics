"""Transparent prototype scoring. Weights and cutoffs require institutional validation."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

WEIGHTS = {"academic": 0.30, "attendance": 0.20, "lms": 0.15, "placement": 0.20, "skills_engagement": 0.10, "support_feedback": 0.05}
MIN_COVERAGE = 0.70


def _number(row: pd.Series, names: tuple[str, ...]) -> float | None:
    for name in names:
        value = row.get(name)
        if pd.isna(value):
            continue
        try:
            result = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(result):
            return result
    return None


def _bounded(value: float | None, low: float, high: float) -> float | None:
    return (value - low) / (high - low) * 100 if value is not None and low <= value <= high else None


def score_student(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    row = pd.Series(row)
    raw: dict[str, dict[str, Any]] = {}
    marks = _number(row, ("academic_marks", "academic_marks_pct"))
    cgpa = _number(row, ("cgpa", "current_cgpa", "gpa"))
    academic = _bounded(marks, 0, 100) if marks is not None else _bounded(cgpa, 0, 10)
    raw["academic"] = {"score": academic, "inputs": {"academic_marks": marks, "cgpa": cgpa}, "explanation": "Academic marks on a 0-100 scale, or legacy CGPA normalized from 0-10."}

    attendance = _number(row, ("attendance_pct", "attendance_percentage", "attendance"))
    raw["attendance"] = {"score": _bounded(attendance, 0, 100), "inputs": {"attendance_pct": attendance}, "explanation": "Attendance percentage on a 0–100 scale."}

    assignment = _number(row, ("assignment_completion_pct", "assignment_completion", "assignments_completed_pct"))
    lms = _number(row, ("lms_activity_score",))
    lms = lms if lms is not None else assignment
    raw["lms"] = {"score": _bounded(lms, 0, 100), "inputs": {"lms_activity_score": lms, "assignment_completion_pct": assignment}, "explanation": "Documented LMS activity score or assignment completion on a 0-100 scale."}

    placement_inputs = {
        "aptitude": _number(row, ("aptitude_score", "aptitude_pct")),
        "coding": _number(row, ("coding_score", "coding_pct")),
        "interview": _number(row, ("mock_interview_score", "interview_score")),
    }
    placement_parts = [_bounded(v, 0, 100) for v in placement_inputs.values()]
    valid_placement = [v for v in placement_parts if v is not None]
    readiness = _number(row, ("placement_readiness_score",))
    raw["placement"] = {"score": _bounded(readiness, 0, 100) if readiness is not None else (float(np.mean(valid_placement)) if valid_placement else None), "inputs": {**placement_inputs, "placement_readiness_score": readiness}, "explanation": "Placement readiness score or mean of available assessments."}

    skill_inputs = {
        "technical_skills": _number(row, ("technical_skills_score", "technical_score")),
        "soft_skills": _number(row, ("soft_skills_score", "soft_skill_score")),
        "engagement": _number(row, ("engagement_score", "activity_score")),
    }
    skill_parts = [_bounded(v, 0, 100) for v in skill_inputs.values()]
    valid_skills = [v for v in skill_parts if v is not None]
    skills = _number(row, ("skills_score",))
    raw["skills_engagement"] = {"score": _bounded(skills, 0, 100) if skills is not None else (float(np.mean(valid_skills)) if valid_skills else None), "inputs": {**skill_inputs, "skills_score": skills}, "explanation": "Skills score or mean of available assessment scores."}

    feedback = _number(row, ("support_feedback_score", "skills_feedback_score", "feedback_score"))
    feedback_norm = _bounded(feedback, 0, 5) if feedback is not None and feedback <= 5 else _bounded(feedback, 0, 100)
    raw["support_feedback"] = {"score": feedback_norm, "inputs": {"feedback_score": feedback}, "explanation": "Feedback normalized from 0–5 when value is at most 5, otherwise from 0–100; confirm source scale before use."}

    valid_weight = sum(WEIGHTS[k] for k, component in raw.items() if component["score"] is not None)
    weighted = sum(WEIGHTS[k] * component["score"] for k, component in raw.items() if component["score"] is not None)
    score = round(weighted / valid_weight, 2) if valid_weight >= MIN_COVERAGE else None
    return {"success_score": score, "score_status": "provisional" if score is not None and valid_weight < 1 else ("complete" if score is not None else "insufficient_data"),
            "coverage": round(valid_weight, 4), "minimum_coverage": MIN_COVERAGE,
            "components": {k: {**v, "weight": WEIGHTS[k]} for k, v in raw.items()}}


def score_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [score_student(row) for _, row in frame.iterrows()]
