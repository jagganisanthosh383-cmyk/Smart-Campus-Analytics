"""Explainable risk flags and overlapping support segments."""
from __future__ import annotations

from typing import Any

import pandas as pd


def assess_risk(student: dict[str, Any]) -> dict[str, Any]:
    def val(*keys: str) -> float | None:
        ranges = {"attendance_pct": (0, 100), "attendance_percentage": (0, 100), "attendance": (0, 100),
                  "cgpa": (0, 10), "current_cgpa": (0, 10), "gpa": (0, 10),
                  "assignment_completion_pct": (0, 100), "assignment_completion": (0, 100), "assignments_completed_pct": (0, 100),
                  "backlogs": (0, None), "backlog_count": (0, None)}
        bounds = next((ranges[k] for k in keys if k in ranges), (0, 100))
        for key in keys:
            try:
                v = student.get(key)
                if v is not None and str(v).strip() != "":
                    result = float(v)
                    if result < bounds[0] or (bounds[1] is not None and result > bounds[1]): return None
                    return result
            except (ValueError, TypeError):
                pass
        return None
    academic, placement = [], []
    attendance = val("attendance_pct", "attendance_percentage", "attendance")
    cgpa = val("cgpa", "current_cgpa", "gpa")
    backlog = val("backlogs", "backlog_count")
    assignment = val("assignment_completion_pct", "assignment_completion", "assignments_completed_pct")
    if attendance is not None and attendance < 65:
        academic.append({"rule": "low_attendance", "evidence": {"attendance_pct": attendance}, "reason": "Attendance is below the example 65% threshold."})
    if cgpa is not None and cgpa < 6:
        academic.append({"rule": "low_cgpa", "evidence": {"cgpa": cgpa}, "reason": "CGPA is below the example 6/10 threshold."})
    if backlog is not None and backlog > 0:
        academic.append({"rule": "recorded_backlogs", "evidence": {"backlogs": backlog}, "reason": "One or more backlogs are recorded."})
    if assignment is not None and assignment < 50:
        academic.append({"rule": "low_assignment_completion", "evidence": {"assignment_completion_pct": assignment}, "reason": "Assignment completion is below the example 50% threshold."})
    for key, aliases in (("aptitude", ("aptitude_score", "aptitude_pct")), ("coding", ("coding_score", "coding_pct")), ("interview", ("mock_interview_score", "interview_score"))):
        value = val(*aliases)
        if value is not None and value < 40:
            placement.append({"rule": f"low_{key}", "evidence": {f"{key}_score": value}, "reason": f"Recorded {key} assessment is below the example 40/100 threshold."})

    academic_present = any(v is not None for v in (attendance, cgpa, backlog, assignment))
    placement_present = any(val(*keys) is not None for keys in (("aptitude_score", "aptitude_pct"), ("coding_score", "coding_pct"), ("mock_interview_score", "interview_score")))
    def category(flags: list, present: bool) -> dict[str, Any]:
        if flags:
            severity = "high" if len(flags) >= 2 else "moderate"
            return {"category": "risk", "severity": severity, "triggered_rules": flags, "reason": "One or more observed indicators met an example review threshold."}
        if not present:
            return {"category": "needs_assessment", "severity": "unknown", "triggered_rules": [], "reason": "Relevant assessment data is unavailable; this is not a low-risk result."}
        return {"category": "no_observed_flag", "severity": "none", "triggered_rules": [], "reason": "No configured example threshold was triggered by the available indicators."}
    return {"academic": category(academic, academic_present), "placement": category(placement, placement_present)}


def segment_membership(student: dict[str, Any]) -> list[dict[str, str]]:
    risk = assess_risk(student)
    def get(*keys):
        for key in keys:
            try:
                if student.get(key) is not None: return float(student[key])
            except (ValueError, TypeError): pass
        return None
    cgpa = get("cgpa", "current_cgpa", "gpa")
    readiness = [get("aptitude_score", "aptitude_pct"), get("coding_score", "coding_pct"), get("mock_interview_score", "interview_score")]
    valid = [x for x in readiness if x is not None]
    segments = []
    if cgpa is not None and cgpa >= 7 and valid and sum(valid) / len(valid) < 50:
        segments.append({"name": "Strong academics, lower placement readiness", "evidence": "CGPA >= 7 and available placement assessment mean < 50.", "action": "Offer placement preparation support."})
    if get("attendance_pct", "attendance_percentage", "attendance") is not None and get("attendance_pct", "attendance_percentage", "attendance") < 65 and get("assignment_completion_pct", "assignment_completion") is not None and get("assignment_completion_pct", "assignment_completion") < 50:
        segments.append({"name": "Low attendance and incomplete coursework", "evidence": "Attendance < 65% and assignment completion < 50%.", "action": "Arrange a faculty check-in and learning plan."})
    if risk["academic"]["category"] == "needs_assessment" or risk["placement"]["category"] == "needs_assessment":
        segments.append({"name": "Insufficient data for assessment", "evidence": "At least one risk domain lacks relevant observations.", "action": "Verify and collect missing assessment data."})
    if risk["academic"]["triggered_rules"]:
        segments.append({"name": "Students needing a faculty check-in", "evidence": "One or more academic review rules triggered.", "action": "Review the evidence with the student and offer appropriate support."})
    if cgpa is not None and cgpa >= 7 and valid and sum(valid) / len(valid) >= 70:
        segments.append({"name": "High academic and placement readiness", "evidence": "CGPA >= 7 and available placement assessment mean >= 70.", "action": "Discuss advanced opportunities and peer support."})
    return segments
