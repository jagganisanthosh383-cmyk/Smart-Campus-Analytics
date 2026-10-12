"""Human-reviewed, evidence-linked support suggestions."""
from __future__ import annotations

from typing import Any


def recommendations_for(student: dict[str, Any]) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    def add(indicator: str, reason: str, action: str) -> None:
        recs.append({"indicator": indicator, "reason": reason, "action": action, "review_required": "true"})

    def num(*keys: str) -> float | None:
        ranges = {"attendance_pct": (0, 100), "attendance_percentage": (0, 100), "attendance": (0, 100),
                  "cgpa": (0, 10), "current_cgpa": (0, 10), "gpa": (0, 10),
                  "assignment_completion_pct": (0, 100), "assignment_completion": (0, 100), "assignments_completed_pct": (0, 100),
                  "backlogs": (0, None), "backlog_count": (0, None)}
        bounds = next((ranges[k] for k in keys if k in ranges), (0, 100))
        for key in keys:
            try:
                value = student.get(key)
                if value is not None and str(value).strip() != "":
                    result = float(value)
                    if result < bounds[0] or (bounds[1] is not None and result > bounds[1]): continue
                    return result
            except (ValueError, TypeError):
                pass
        return None

    attendance = num("attendance_pct", "attendance_percentage", "attendance")
    if attendance is not None and attendance < 65:
        add("attendance_pct", f"Recorded attendance is {attendance:g}%.", "Offer a faculty check-in and verify the attendance record.")
    marks = num("academic_marks")
    if marks is not None and marks < 60:
        add("academic_marks", f"Recorded academic marks are {marks:g}/100.", "Offer subject tutoring and academic advising.")
    cgpa = num("cgpa", "current_cgpa", "gpa")
    backlogs = num("backlogs", "backlog_count")
    if (cgpa is not None and cgpa < 6) or (backlogs is not None and backlogs > 0):
        add("cgpa/backlogs", "CGPA is below the example threshold or backlogs are recorded.", "Offer subject tutoring and academic advising.")
    assignment = num("assignment_completion_pct", "assignment_completion", "assignments_completed_pct")
    if assignment is not None and assignment < 50:
        add("assignment_completion_pct", f"Assignment completion is {assignment:g}%.", "Offer learning support and help plan upcoming assignments.")
    lms = num("lms_activity_score")
    if lms is not None and lms < 50:
        add("lms_activity_score", f"Recorded LMS activity score is {lms:g}/100.", "Review course participation with the student and plan targeted learning support.")
    readiness = num("placement_readiness_score")
    if readiness is not None and readiness < 40:
        add("placement_readiness_score", f"Recorded placement readiness is {readiness:g}/100.", "Offer structured placement preparation and mentor support.")
    skills = num("skills_score")
    if skills is not None and skills < 50:
        add("skills_score", f"Recorded skills score is {skills:g}/100.", "Discuss a focused skills practice plan and available mentoring.")
    coding = num("coding_score", "coding_pct")
    aptitude = num("aptitude_score", "aptitude_pct")
    interview = num("mock_interview_score", "interview_score")
    if coding is not None and coding < 40:
        add("coding_score", f"Recorded coding assessment is {coding:g}/100.", "Offer structured coding practice and mentor support.")
    if aptitude is not None and aptitude < 40:
        add("aptitude_score", f"Recorded aptitude assessment is {aptitude:g}/100.", "Offer targeted aptitude practice exercises.")
    if interview is not None and interview < 40:
        add("mock_interview_score", f"Recorded interview assessment is {interview:g}/100.", "Offer a mock interview and communication coaching.")
    if all(v is None for v in (attendance, cgpa, marks, assignment, lms, readiness, skills, coding, aptitude, interview)):
        add("assessment_data", "Relevant risk assessments are not present in the available record.", "Verify source data or arrange the missing assessment before drawing conclusions.")
    return recs
