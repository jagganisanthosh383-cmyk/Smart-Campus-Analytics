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
NUMERIC_RANGES: dict[str, tuple[tuple[str, ...], float, float]] = {
    "academics": (("cgpa", "current_cgpa", "gpa"), 0, 10),
    "attendance": (("attendance_pct", "attendance_percentage", "attendance"), 0, 100),
    "lms": (("assignment_completion_pct", "assignment_completion", "assignments_completed_pct"), 0, 100),
    "placement": (("aptitude_score", "aptitude_pct", "coding_score", "coding_pct", "mock_interview_score", "interview_score"), 0, 100),
    "skills": (("technical_skills_score", "technical_score", "soft_skills_score", "soft_skill_score"), 0, 100),
    "engagement": (("engagement_score", "activity_score"), 0, 100),
}


class DataValidationError(ValueError):
    """A source exists but cannot safely be integrated."""


def inspect_sources(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    """Return deterministic source presence, schema, and record-quality details."""
    result: dict[str, Any] = {"data_dir": str(data_dir), "sources": {}, "errors": [], "warnings": []}
    for name, required in SOURCES.items():
        path = data_dir / f"{name}.csv"
        item: dict[str, Any] = {"file": path.name, "present": path.is_file()}
        if path.is_file():
            try:
                frame = pd.read_csv(path, dtype={"student_id": "string"})
                missing = [col for col in required if col not in frame.columns]
                if "student_id" in frame:
                    ids = frame["student_id"].str.strip()
                    frame["student_id"] = ids
                    duplicate_groups = frame[frame["student_id"].duplicated(keep=False)].groupby("student_id", dropna=False)
                    conflicts = sum(1 for _, group in duplicate_groups if len(group.drop(columns=["student_id"]).drop_duplicates()) > 1)
                else:
                    conflicts = 0
                invalid_values = {}
                rule = NUMERIC_RANGES.get(name)
                if rule:
                    candidates, low, high = rule
                    for column in candidates:
                        if column in frame.columns:
                            raw = frame[column]
                            numeric = pd.to_numeric(raw, errors="coerce")
                            bad = raw.notna() & (numeric.isna() | (numeric < low) | (numeric > high))
                            if int(bad.sum()):
                                invalid_values[column] = int(bad.sum())
                item.update(rows=len(frame), columns=list(frame.columns), missing_columns=missing,
                            missing_student_ids=int((frame["student_id"].isna() | frame["student_id"].eq("")).sum()) if "student_id" in frame else None,
                            duplicate_student_ids=int(frame["student_id"].duplicated(keep=False).sum()) if "student_id" in frame else None,
                            conflicting_student_id_groups=conflicts,
                            invalid_values=invalid_values)
                if missing:
                    result["errors"].append(f"{name}.csv missing required columns: {', '.join(missing)}")
            except Exception:
                # Keep filesystem paths and parser internals out of the API report.
                item["read_error"] = "CSV could not be parsed"
                result["errors"].append(f"Could not read {name}.csv")
        else:
            item.update(rows=None, columns=[], missing_columns=[], missing_student_ids=None, duplicate_student_ids=None, conflicting_student_id_groups=None, invalid_values={})
            if name == "students":
                result["errors"].append("Required source students.csv is missing")
            else:
                result["warnings"].append(f"Optional source {name}.csv is missing")
        result["sources"][name] = item
    result["student_records_available"] = bool(result["sources"]["students"]["present"] and not result["errors"])
    return result


def load_students(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Load the student base table, or an empty frame when no data is available."""
    path = data_dir / "students.csv"
    if not path.is_file():
        return pd.DataFrame(columns=["student_id"])
    try:
        frame = pd.read_csv(path, dtype={"student_id": "string"})
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
    students = load_students(data_dir)
    quality = inspect_sources(data_dir)
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
            source = pd.read_csv(path, dtype={"student_id": "string"})
            if "student_id" not in source.columns:
                quality["excluded_sources"].append({"source": name, "reason": "missing student_id"})
                continue
            source["student_id"] = source["student_id"].str.strip()
            if (source["student_id"].isna() | source["student_id"].eq("")).any() or source["student_id"].duplicated().any():
                quality["excluded_sources"].append({"source": name, "reason": "blank or duplicate student_id"})
                quality["missing_source_rows"][name] = len(merged)
                continue
            source_ids = set(source["student_id"].astype(str))
            quality["orphans"][name] = len(source_ids - roster_ids)
            quality["missing_source_rows"][name] = len(roster_ids - source_ids)
            source = source[source["student_id"].isin(roster_ids)].copy()
            collisions = [col for col in source.columns if col != "student_id" and col in merged.columns]
            source = source.rename(columns={col: f"{name}_{col}" for col in collisions})
            merged = merged.merge(source, on="student_id", how="left", validate="one_to_one")
        except Exception:
            quality["excluded_sources"].append({"source": name, "reason": "CSV could not be read or joined"})
            quality["missing_source_rows"][name] = len(merged)
    quality["integrated_student_count"] = len(merged)
    quality["score_coverage"] = 0.0
    return merged, quality
