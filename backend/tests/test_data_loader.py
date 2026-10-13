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


def test_all_eight_demo_sources_are_valid_and_reported_by_methodology():
    from backend.data_loader import DATA_DIR
    report = inspect_sources(DATA_DIR)
    assert report["expected_source_count"] == report["detected_source_count"] == 8
    assert report["missing_sources"] == report["invalid_sources"] == []
    app = create_app(); app.config["DATA_DIR"] = DATA_DIR
    methodology = app.test_client().get("/api/methodology").json
    assert methodology["detected_source_count"] == 8
    assert methodology["minimum_score_coverage"] == 0.70
    assert methodology["weights"] == {"academic": .3, "attendance": .2, "lms": .15, "placement": .2, "skills_engagement": .1, "support_feedback": .05}
    assert any("synthetic" in x.lower() for x in methodology["limitations"])


def test_missing_and_invalid_sources_are_separately_reported(tmp_path: Path):
    pd.DataFrame({"student_id": ["S1"]}).to_csv(tmp_path / "students.csv", index=False)
    (tmp_path / "academics.csv").write_text("student_id,unknown_metric\nS1,1\n", encoding="utf-8")
    (tmp_path / "attendance.csv").write_text('student_id,attendance_pct\n"unterminated,70\n', encoding="utf-8")
    report = inspect_sources(tmp_path)
    assert "academics" in report["invalid_sources"]
    assert "attendance" in report["invalid_sources"]
    assert "lms" in report["missing_sources"]
    assert report["sources"]["academics"]["valid"] is False


def test_missing_values_stay_missing_and_coverage_threshold_statuses():
    score = score_student({"cgpa": 8, "attendance_pct": None, "assignment_completion_pct": 90,
                           "aptitude_score": 75, "coding_score": None, "mock_interview_score": 70})
    assert score["coverage"] == pytest.approx(.65)
    assert score["success_score"] is None
    adequate = score_student({"cgpa": 8, "attendance_pct": 90, "assignment_completion_pct": 80,
                              "aptitude_score": 75, "coding_score": 70, "mock_interview_score": 72})
    assert adequate["coverage"] == pytest.approx(.85)
    assert adequate["success_score"] is not None
    assert adequate["score_status"] == "provisional"


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
    assert client.get("/api/methodology").json["detected_source_count"] == 1
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


def test_demo_roster_display_headers_and_dashboard_metrics():
    from backend.data_loader import DATA_DIR, load_dataset
    expected = [f"25D01A66{i:02}" for i in range(1, 11)]
    frame, _ = load_dataset(DATA_DIR)
    assert frame.student_id.tolist() == expected
    assert frame.department.eq("CSE AIML").all()
    app = create_app(); app.config["DATA_DIR"] = DATA_DIR; client = app.test_client()
    roster = client.get("/api/students?per_page=20").json
    assert roster["total"] == 10
    assert roster["items"][0]["name"] == "Aarav Mehta"
    assert roster["items"][0]["score"]["success_score"] is not None
    assert roster["items"][0]["risk_level"] == "Low"
    summary = client.get("/api/dashboard/summary").json
    assert summary["total_students"] == 10
    assert summary["average_attendance"] == pytest.approx(frame.attendance_pct.astype(float).mean())
    assert summary["average_academic_marks"] == pytest.approx(frame.academic_marks.astype(float).mean())
    assert summary["high_risk_student_count"] == 2
    assert summary["mean_success_score"] is not None


def test_missing_roster_returns_actionable_api_error(tmp_path: Path):
    app = create_app(); app.config["DATA_DIR"] = tmp_path; client = app.test_client()
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 503
    assert "students.csv is missing" in response.json["error"]
    assert client.get("/api/students").status_code == 503
    assert client.get("/api/students/export").status_code == 503


def test_invalid_demo_measurement_is_reported_instead_of_becoming_zero(tmp_path: Path):
    pd.DataFrame({"Student ID": ["S1"], "Attendance": [140]}).to_csv(tmp_path / "students.csv", index=False)
    app = create_app(); app.config["DATA_DIR"] = tmp_path; client = app.test_client()
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 422
    assert "invalid numeric values" in response.json["error"]
    assert client.get("/api/students").status_code == 422
    assert client.get("/api/students/export").status_code == 422
