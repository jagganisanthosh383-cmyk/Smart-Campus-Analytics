"""Load and validate CampusPulse CSV sources without inventing measurements."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import os

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("CAMPUSPULSE_DATA_DIR", PROJECT_ROOT / "backend" / "data")).resolve()

# These schemas are logical expectations; optional sources may be absent.
SOURCES: dict[str, tuple[str, ...]] = {
    "students": ("student_id",),
    "academics": ("student_id",),
    "attendance": ("student_id",),
    "lms": ("student_id",),
    "engagement": ("student_id",),
    "placement": ("student_id",),
    "skills": ("student_id",),
    "skills_feedback": ("student_id",),
}
SOURCE_MEASUREMENTS: dict[str, tuple[str, ...]] = {
    "academics": ("academic_marks", "cgpa", "current_cgpa", "gpa"),
    "attendance": ("attendance_pct", "attendance_percentage", "attendance"),
    "lms": ("lms_activity_score", "assignment_completion_pct", "assignment_completion", "assignments_completed_pct"),
    "engagement": ("engagement_score", "activity_score"),
    "placement": ("placement_readiness_score", "aptitude_score", "aptitude_pct", "coding_score", "coding_pct", "mock_interview_score", "interview_score"),
    "skills": ("skills_score", "technical_skills_score", "technical_score", "soft_skills_score", "soft_skill_score"),
    "skills_feedback": ("support_feedback_score", "skills_feedback_score", "feedback_score"),
}
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "student_id": ("student_id", "student id"),
    "name": ("name", "student name"),
    "department": ("department",),
    "attendance_pct": ("attendance_pct", "attendance percentage", "attendance"),
    "academic_marks": ("academic_marks", "academic marks"),
    "lms_activity_score": ("lms_activity_score", "lms activity"),
    "placement_readiness_score": ("placement_readiness_score", "placement readiness"),
    "skills_score": ("skills_score", "skills score"),
    "success_score": ("success_score", "success score"),
    "risk_level": ("risk_level", "risk level"),
    "recommended_intervention": ("recommended_intervention", "recommended intervention"),
    "cgpa": ("cgpa", "current cgpa", "gpa"),
    "assignment_completion_pct": ("assignment_completion_pct", "assignment completion", "assignments completed pct"),
}


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Map display-style CSV headers to API field names without dropping columns."""
    def key(value: str) -> str:
        return "".join(char for char in value.casefold() if char.isalnum())

    normalized = frame.copy()
    by_key = {key(str(column)): str(column) for column in normalized.columns}
    renames: dict[str, str] = {}
    for target, aliases in HEADER_ALIASES.items():
        if target in normalized.columns:
            continue
        for alias in aliases:
            source = by_key.get(key(alias))
            if source is not None and source not in renames:
                renames[source] = target
                break
    return normalized.rename(columns=renames)
NUMERIC_RANGES: dict[str, tuple[tuple[str, ...], float, float]] = {
    "students": (("attendance_pct", "academic_marks", "lms_activity_score", "placement_readiness_score", "skills_score", "success_score"), 0, 100),
    "academics": (("cgpa", "current_cgpa", "gpa"), 0, 10),
    "attendance": (("attendance_pct", "attendance_percentage", "attendance"), 0, 100),
    "lms": (("assignment_completion_pct", "assignment_completion", "assignments_completed_pct"), 0, 100),
    "placement": (("aptitude_score", "aptitude_pct", "coding_score", "coding_pct", "mock_interview_score", "interview_score"), 0, 100),
    "skills": (("technical_skills_score", "technical_score", "soft_skills_score", "soft_skill_score"), 0, 100),
    "engagement": (("engagement_score", "activity_score"), 0, 100),
}


class DataValidationError(ValueError):
    """A source exists but cannot safely be integrated."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def inspect_sources(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    """Return deterministic source presence, schema, and record-quality details."""
    result: dict[str, Any] = {"data_dir": str(data_dir), "sources": {}, "errors": [], "warnings": []}
    for name, required in SOURCES.items():
        path = data_dir / f"{name}.csv"
        item: dict[str, Any] = {"file": path.name, "present": path.is_file(), "valid": False}
        if path.is_file():
            try:
                frame = pd.read_csv(path, dtype={"student_id": "string", "Student ID": "string"})
                normalized = normalize_columns(frame)
                missing = [col for col in required if col not in normalized.columns]
                missing_measurements = []
                expected_measurements = SOURCE_MEASUREMENTS.get(name, ())
                if expected_measurements and not any(col in normalized.columns for col in expected_measurements):
                    missing_measurements = list(expected_measurements)
                if "student_id" in normalized:
                    ids = normalized["student_id"].astype("string").str.strip()
                    normalized["student_id"] = ids
                    duplicate_groups = normalized[normalized["student_id"].duplicated(keep=False)].groupby("student_id", dropna=False)
                    conflicts = sum(1 for _, group in duplicate_groups if len(group.drop(columns=["student_id"]).drop_duplicates()) > 1)
                else:
                    conflicts = 0
                invalid_values = {}
                rule = NUMERIC_RANGES.get(name)
                if rule:
                    candidates, low, high = rule
                    for column in candidates:
                        if column in normalized.columns:
                            raw = normalized[column]
                            numeric = pd.to_numeric(raw, errors="coerce")
                            bad = raw.notna() & (numeric.isna() | (numeric < low) | (numeric > high))
                            if int(bad.sum()):
                                invalid_values[column] = int(bad.sum())
                item.update(rows=len(frame), columns=list(frame.columns), missing_columns=missing,
                            missing_measurements=missing_measurements,
                            missing_student_ids=int((normalized["student_id"].isna() | normalized["student_id"].eq("")).sum()) if "student_id" in normalized else None,
                            duplicate_student_ids=int(normalized["student_id"].duplicated(keep=False).sum()) if "student_id" in normalized else None,
                            conflicting_student_id_groups=conflicts,
                            invalid_values=invalid_values)
                if missing:
                    result["errors"].append(f"{name}.csv missing required columns: {', '.join(missing)}")
                if missing_measurements:
                    result["errors"].append(f"{name}.csv has no recognized measurement column")
                structurally_valid = not missing and not missing_measurements and not item.get("missing_student_ids") and not item.get("duplicate_student_ids")
                item["valid"] = bool(structurally_valid)
                if missing or missing_measurements or item.get("missing_student_ids") or item.get("duplicate_student_ids"):
                    item["validation_error"] = "Required columns or unique nonblank student IDs are invalid"
                    if item.get("missing_student_ids"):
                        result["errors"].append(f"{name}.csv contains blank student_id values")
                    if item.get("duplicate_student_ids"):
                        result["errors"].append(f"{name}.csv contains duplicate student_id values")
            except Exception:
                # Keep filesystem paths and parser internals out of the API report.
                item["read_error"] = "CSV could not be parsed"
                item["valid"] = False
                result["errors"].append(f"Could not read {name}.csv")
        else:
            item.update(rows=None, columns=[], missing_columns=[], missing_student_ids=None, duplicate_student_ids=None, conflicting_student_id_groups=None, invalid_values={})
            if name == "students":
                result["errors"].append("Required source students.csv is missing")
            else:
                result["warnings"].append(f"Optional source {name}.csv is missing")
        result["sources"][name] = item
    roster = result["sources"]["students"]
    result["student_records_available"] = bool(roster["present"] and roster["valid"])
    result["expected_source_count"] = len(SOURCES)
    result["detected_source_count"] = sum(source["valid"] for source in result["sources"].values())
    result["detected_sources"] = [name for name, source in result["sources"].items() if source["valid"]]
    result["missing_sources"] = [name for name, source in result["sources"].items() if not source["present"]]
    result["invalid_sources"] = [name for name, source in result["sources"].items() if source["present"] and not source["valid"]]
    return result


def load_students(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Load the student base table, or an empty frame when no data is available."""
    path = data_dir / "students.csv"
    if not path.is_file():
        return pd.DataFrame(columns=["student_id"])
    try:
        frame = normalize_columns(pd.read_csv(path, dtype={"student_id": "string", "Student ID": "string"}))
    except Exception as exc:
        raise DataValidationError("students.csv could not be read") from exc
    if "student_id" not in frame.columns:
        raise DataValidationError("students.csv must contain student_id")
    frame["student_id"] = frame["student_id"].str.strip()
    if (frame["student_id"].isna() | frame["student_id"].eq("")).any():
        raise DataValidationError("students.csv contains blank student_id values")
    if frame["student_id"].duplicated().any():
        raise DataValidationError("students.csv contains duplicate student_id values")
    return frame


def load_dataset(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Left-join valid sources to students without multiplying or dropping students.

    Duplicate or malformed optional sources are excluded and described in quality
    metadata. The students table is required and treated as the authoritative roster.
    """
    if not (data_dir / "students.csv").is_file():
        raise DataValidationError("Required source students.csv is missing", status_code=503)
    students = load_students(data_dir)
    quality = inspect_sources(data_dir)
    student_source = quality["sources"]["students"]
    if student_source.get("missing_columns"):
        raise DataValidationError("students.csv missing required columns: " + ", ".join(student_source["missing_columns"]))
    if student_source.get("invalid_values"):
        invalid = ", ".join(f"{column} ({count} rows)" for column, count in student_source["invalid_values"].items())
        raise DataValidationError(f"students.csv contains invalid numeric values: {invalid}")
    merged = students.copy()
    merged["student_id"] = merged["student_id"].astype("string").str.strip()
    roster_ids = set(merged["student_id"].astype(str))
    quality["orphans"] = {}
    quality["missing_source_rows"] = {}
    quality["excluded_sources"] = []

    for name in SOURCES:
        if name == "students":
            continue
        path = data_dir / f"{name}.csv"
        if not path.is_file():
            quality["missing_source_rows"][name] = len(merged)
            continue
        try:
            source = normalize_columns(pd.read_csv(path, dtype={"student_id": "string", "Student ID": "string"}))
            if "student_id" not in source.columns:
                quality["excluded_sources"].append({"source": name, "reason": "missing student_id"})
                continue
            source["student_id"] = source["student_id"].str.strip()
            if (source["student_id"].isna() | source["student_id"].eq("")).any() or source["student_id"].duplicated().any():
                quality["excluded_sources"].append({"source": name, "reason": "blank or duplicate student_id"})
                quality["missing_source_rows"][name] = len(merged)
                continue
            if quality["sources"][name].get("missing_measurements"):
                quality["excluded_sources"].append({"source": name, "reason": "no recognized measurement column"})
                continue
            source_ids = set(source["student_id"].astype(str))
            quality["orphans"][name] = len(source_ids - roster_ids)
            quality["missing_source_rows"][name] = len(roster_ids - source_ids)
            source = source[source["student_id"].isin(roster_ids)].copy()
            collisions = [col for col in source.columns if col != "student_id" and col in merged.columns]
            # Prefer explicit supplemental source measurements while retaining
            # the unchanged roster values under a namespaced field.
            merged = merged.rename(columns={col: f"students_{col}" for col in collisions})
            merged = merged.merge(source, on="student_id", how="left", validate="one_to_one")
        except Exception:
            quality["excluded_sources"].append({"source": name, "reason": "CSV could not be read or joined"})
            quality["missing_source_rows"][name] = len(merged)
    quality["integrated_student_count"] = len(merged)
    quality["score_coverage"] = 0.0
    return merged, quality
