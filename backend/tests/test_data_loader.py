from pathlib import Path

import pandas as pd
import pytest

from backend.data_loader import DataValidationError, inspect_sources, load_dataset, load_students
from backend.analytics import assess_risk, segment_membership
from backend.main import create_app
from backend.recommendations import recommendations_for
from backend.scoring import score_student


def test_empty_data_dir_is_reported_without_fake_data(tmp_path: Path):
    report = inspect_sources(tmp_path)
    assert report["student_records_available"] is False
    assert report["sources"]["students"]["present"] is False
    assert load_students(tmp_path).empty


def test_student_ids_must_be_unique_and_present(tmp_path: Path):
    pd.DataFrame({"student_id": ["S1", "S1"]}).to_csv(tmp_path / "students.csv", index=False)
    with pytest.raises(DataValidationError, match="duplicate"):
        load_students(tmp_path)

    pd.DataFrame({"student_id": ["S1", None]}).to_csv(tmp_path / "students.csv", index=False)
    with pytest.raises(DataValidationError, match="blank"):
        load_students(tmp_path)


def test_required_column_is_reported(tmp_path: Path):
    pd.DataFrame({"id": ["S1"]}).to_csv(tmp_path / "students.csv", index=False)
    report = inspect_sources(tmp_path)
    assert report["sources"]["students"]["missing_columns"] == ["student_id"]
    with pytest.raises(DataValidationError, match="student_id"):
        load_students(tmp_path)


def test_sources_left_join_without_multiplication_and_report_orphans(tmp_path: Path):
    pd.DataFrame({"student_id": ["S1", "S2"], "department": ["CSE", "ECE"]}).to_csv(tmp_path / "students.csv", index=False)
    pd.DataFrame({"student_id": ["S1", "S3"], "attendance_pct": [88, 77]}).to_csv(tmp_path / "attendance.csv", index=False)
    frame, quality = load_dataset(tmp_path)
    assert len(frame) == 2
    assert frame.loc[frame.student_id == "S2", "attendance_pct"].isna().all()
    assert quality["orphans"]["attendance"] == 1
    assert quality["sources"]["attendance"]["file"] == "attendance.csv"


def test_duplicate_optional_source_is_excluded(tmp_path: Path):
    pd.DataFrame({"student_id": ["S1"]}).to_csv(tmp_path / "students.csv", index=False)
    pd.DataFrame({"student_id": ["S1", "S1"], "score": [60, 70]}).to_csv(tmp_path / "placement.csv", index=False)
    frame, quality = load_dataset(tmp_path)
    assert len(frame) == 1
    assert "score" not in frame
    assert {"source": "placement", "reason": "blank or duplicate student_id"} in quality["excluded_sources"]


def test_quality_reports_invalid_measurements_and_missing_source_rows(tmp_path: Path):
    pd.DataFrame({"student_id": ["S1", "S2"]}).to_csv(tmp_path / "students.csv", index=False)
    pd.DataFrame({"student_id": ["S1", "S3"], "attendance_pct": [120, "unknown"]}).to_csv(tmp_path / "attendance.csv", index=False)
    _, quality = load_dataset(tmp_path)
    assert quality["sources"]["attendance"]["invalid_values"]["attendance_pct"] == 2
    assert quality["missing_source_rows"]["attendance"] == 1
    assert quality["orphans"]["attendance"] == 1


def test_score_weights_coverage_and_bounds():
    scored = score_student({"cgpa": 8, "attendance_pct": 100, "assignment_completion_pct": 100,
                            "aptitude_score": 100, "coding_score": 100, "mock_interview_score": 100})
    assert scored["success_score"] == 92.94
    assert scored["coverage"] == 0.85
    assert scored["score_status"] == "provisional"
    assert score_student({"attendance_pct": 100})["success_score"] is None
    assert score_student({"cgpa": 11})["components"]["academic"]["score"] is None


def test_risks_need_assessment_and_recommendations_are_evidence_based():
    empty = assess_risk({})
    assert empty["academic"]["category"] == "needs_assessment"
    assert empty["placement"]["category"] == "needs_assessment"
    student = {"attendance_pct": 50, "cgpa": 5.5, "coding_score": 20, "assignment_completion_pct": 30}
    result = assess_risk(student)
    assert {r["rule"] for r in result["academic"]["triggered_rules"]} >= {"low_attendance", "low_cgpa", "low_assignment_completion"}
    recs = recommendations_for(student)
    assert {r["indicator"] for r in recs} >= {"attendance_pct", "cgpa/backlogs", "coding_score", "assignment_completion_pct"}
    assert "Students needing a faculty check-in" in {s["name"] for s in segment_membership(student)}


def test_api_filters_pagination_profiles_and_csv_export(tmp_path: Path):
    pd.DataFrame({"student_id": ["A1", "A2"], "name": ["=HYPERLINK(\"x\")", "Ben"], "department": ["CSE", "ECE"], "year": [2, 3],
                  "cgpa": [8.2, 5.8], "attendance_pct": [90, 55], "assignment_completion_pct": [85, 40],
                  "aptitude_score": [75, 30], "coding_score": [70, 25], "mock_interview_score": [80, 35]}).to_csv(tmp_path / "students.csv", index=False)
    app = create_app(); app.config["DATA_DIR"] = tmp_path; client = app.test_client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/methodology").status_code == 200
    assert client.get("/api/dashboard/summary").json["student_count"] == 2
    assert client.get("/api/students?per_page=1").json["pages"] == 2
    assert len(client.get("/api/students?department=CSE").json["items"]) == 1
    assert client.get("/api/students?risk_only=maybe").status_code == 400
    assert client.get("/api/students?page=0").status_code == 400
    assert client.get("/api/students/A1").status_code == 200
    assert client.get("/api/students/nope").status_code == 404
    assert client.get("/api/students/A2/risk").json["academic"]["category"] == "risk"
    assert client.get("/api/students/A2/recommendations").status_code == 200
    export = client.get("/api/students/export?department=CSE")
    assert "text/csv" in export.content_type
    assert "'=HYPERLINK" in export.get_data(as_text=True)
    assert client.get("/api/students?academic_risk=unknown").status_code == 400
    assert client.get("/api/analytics/departments").status_code == 200
    assert client.get("/api/analytics/risks").status_code == 200


def test_cors_allows_only_configured_frontend_origin(monkeypatch):
    monkeypatch.setenv("CAMPUSPULSE_CORS_ORIGINS", "https://campuspulse.example")
    client = create_app().test_client()
    allowed = client.get("/api/health", headers={"Origin": "https://campuspulse.example"})
    denied = client.get("/api/health", headers={"Origin": "https://other.example"})
    assert allowed.headers.get("Access-Control-Allow-Origin") == "https://campuspulse.example"
    assert denied.headers.get("Access-Control-Allow-Origin") is None
