"""CampusPulse Flask API."""
from __future__ import annotations

import csv
import io
import os
from typing import Any

import pandas as pd
from flask import Flask, Response, jsonify, request

try:
    from .analytics import assess_risk, segment_membership
    from .data_loader import DATA_DIR, DataValidationError, inspect_sources, load_dataset
    from .recommendations import recommendations_for
    from .scoring import MIN_COVERAGE, WEIGHTS, score_student
except ImportError:  # direct ``python backend/main.py`` execution
    from analytics import assess_risk, segment_membership
    from data_loader import DATA_DIR, DataValidationError, inspect_sources, load_dataset
    from recommendations import recommendations_for
    from scoring import MIN_COVERAGE, WEIGHTS, score_student

METHODOLOGY = {
    "title": "CampusPulse prototype methodology",
    "notice": "Prototype rules and weights require institutional validation. Risk flags support human review and are not predictions of failure.",
    "weights": WEIGHTS,
    "minimum_score_coverage": MIN_COVERAGE,
    "thresholds": {"attendance_pct": 65, "cgpa_out_of_10": 6, "academic_marks_out_of_100": 60, "assignment_completion_pct": 50, "placement_assessment_out_of_100": 40, "placement_readiness_out_of_100": 40},
    "missing_data": "Missing indicators are excluded, never replaced with zero. Available weights are renormalized only when coverage is at least 70%; lower coverage returns a null score.",
    "minimum_coverage_rule": "Coverage is the sum of weights for score components with valid measurements. Available component weights are renormalized only at or above 70%; lower coverage has no numeric score. Scores below 100% coverage are provisional.",
    "risk_review": "Example rule-based thresholds require institutional validation. Missing information alone never creates high risk. Recommendations require staff review.",
    "source_purposes": {"students": "Synthetic demo roster and student IDs", "academics": "CGPA or academic marks", "attendance": "Attendance percentage", "lms": "LMS activity or assignment completion", "engagement": "Engagement/activity score", "placement": "Aptitude, coding, interview, or readiness scores", "skills": "Technical and soft skills scores", "skills_feedback": "Support or skills feedback score"},
    "limitations": ["All included student and supplemental records are synthetic demonstration data, not institutional records.", "Rule-based prototype, not a validated predictive model.", "Available data and source measurement scales must be verified with the institution."],
}


def _load(app: Flask):
    return load_dataset(app.config["DATA_DIR"])


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for row in frame.to_dict(orient="records"):
        item = {k: (None if pd.isna(v) else v.item() if hasattr(v, "item") else v) for k, v in row.items()}
        item["score"] = score_student(item)
        item["risk"] = assess_risk(item)
        item["segments"] = segment_membership(item)
        item["success_score"] = item["score"]["success_score"]
        categories = [item["risk"][k]["category"] for k in ("academic", "placement")]
        item["risk_level"] = "High" if any(item["risk"][k]["severity"] == "high" for k in ("academic", "placement")) else ("Medium" if "risk" in categories else ("Needs assessment" if "needs_assessment" in categories else "Low"))
        if not item.get("recommended_intervention"):
            item["recommended_intervention"] = "; ".join(x["action"] for x in recommendations_for(item)) or "Continue routine mentoring and review progress."
        out.append(item)
    return out


def _filtered(records: list[dict], args) -> list[dict]:
    department, year = args.get("department"), args.get("year")
    query = (args.get("search") or "").strip().casefold()
    risk_only = args.get("risk_only", "false").casefold()
    if risk_only not in {"true", "false", "1", "0"}:
        raise ValueError("risk_only must be true or false")
    if len(query) > 200:
        raise ValueError("search must be 200 characters or fewer")
    categories = {"risk", "needs_assessment", "no_observed_flag"}
    for key in ("academic_risk", "placement_risk", "overall_risk"):
        if args.get(key) and args.get(key) not in categories:
            raise ValueError(f"{key} must be one of: {', '.join(sorted(categories))}")
    result = []
    for r in records:
        if department and str(r.get("department", "")) != department: continue
        if year and str(r.get("year", r.get("academic_year", ""))) != year: continue
        if query and query not in " ".join(str(r.get(k, "")) for k in ("student_id", "name", "department")).casefold(): continue
        a, p = r["risk"]["academic"], r["risk"]["placement"]
        overall = "risk" if a["category"] == "risk" or p["category"] == "risk" else ("needs_assessment" if "needs_assessment" in (a["category"], p["category"]) else "no_observed_flag")
        if args.get("academic_risk") and args.get("academic_risk") != a["category"]: continue
        if args.get("placement_risk") and args.get("placement_risk") != p["category"]: continue
        if args.get("overall_risk") and args.get("overall_risk") != overall: continue
        if risk_only in {"true", "1"} and overall == "no_observed_flag": continue
        r["overall_risk"] = overall
        result.append(r)
    return result


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["DATA_DIR"] = DATA_DIR
    origins = [x.strip() for x in os.environ.get("CAMPUSPULSE_CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
    try:
        from flask_cors import CORS
        CORS(app, resources={r"/api/*": {"origins": origins}})
    except ImportError:
        pass

    @app.errorhandler(DataValidationError)
    def invalid_data(error: DataValidationError):
        return jsonify({"error": str(error)}), error.status_code

    @app.errorhandler(500)
    def internal_error(_error):
        app.logger.exception("Unhandled API error")
        return jsonify({"error": "Internal server error"}), 500

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "CampusPulse API"})

    @app.get("/api/methodology")
    def methodology():
        report = inspect_sources(app.config["DATA_DIR"])
        return jsonify({**METHODOLOGY, "sources": report["sources"], "expected_source_count": report["expected_source_count"],
                        "detected_source_count": report["detected_source_count"], "detected_sources": report["detected_sources"],
                        "missing_sources": report["missing_sources"], "invalid_sources": report["invalid_sources"],
                        "available_sources": report["detected_sources"]})

    @app.get("/api/data-quality")
    def data_quality():
        try:
            _frame, report = _load(app)
            return jsonify(report)
        except (DataValidationError, pd.errors.ParserError):
            return jsonify(inspect_sources(app.config["DATA_DIR"])), 200

    @app.get("/api/filters")
    def filters():
        frame, _ = _load(app)
        return jsonify({"departments": sorted(frame.department.dropna().astype(str).unique().tolist()) if "department" in frame else [],
                        "years": sorted((frame.year if "year" in frame else frame.academic_year if "academic_year" in frame else pd.Series(dtype=str)).dropna().astype(str).unique().tolist())})

    @app.get("/api/students")
    def students():
        try:
            page = int(request.args.get("page", 1)); per_page = int(request.args.get("per_page", 25))
            if page < 1 or per_page < 1 or per_page > 200: raise ValueError("page must be positive and per_page must be between 1 and 200")
            frame, _ = _load(app)
            if request.args.get("department") and ("department" not in frame or request.args["department"] not in frame["department"].dropna().astype(str).unique()): raise ValueError("department is not a known filter value")
            year_values = frame["year"].dropna().astype(str).unique() if "year" in frame else frame["academic_year"].dropna().astype(str).unique() if "academic_year" in frame else []
            if request.args.get("year") and request.args["year"] not in year_values: raise ValueError("year is not a known filter value")
            records = _filtered(_records(frame), request.args)
            total = len(records)
            return jsonify({"items": records[(page-1)*per_page:page*per_page], "page": page, "per_page": per_page, "total": total, "pages": (total+per_page-1)//per_page})
        except DataValidationError as exc: return jsonify({"error": str(exc)}), exc.status_code
        except ValueError as exc: return jsonify({"error": str(exc)}), 400

    @app.get("/api/students/export")
    def export_students():
        try:
            frame, _ = _load(app)
            if request.args.get("department") and ("department" not in frame or request.args["department"] not in frame["department"].dropna().astype(str).unique()): raise ValueError("department is not a known filter value")
            year_values = frame["year"].dropna().astype(str).unique() if "year" in frame else frame["academic_year"].dropna().astype(str).unique() if "academic_year" in frame else []
            if request.args.get("year") and request.args["year"] not in year_values: raise ValueError("year is not a known filter value")
            rows = _filtered(_records(frame), request.args)
        except DataValidationError as exc: return jsonify({"error": str(exc)}), exc.status_code
        except ValueError as exc: return jsonify({"error": str(exc)}), 400
        fields = ["student_id", "name", "department", "year", "attendance_pct", "academic_marks", "lms_activity_score", "placement_readiness_score", "skills_score", "success_score", "risk_level", "recommended_intervention", "score_status", "overall_risk"]
        buf = io.StringIO(newline=""); writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore"); writer.writeheader()
        for r in rows:
            line = {**r, "success_score": r["score"]["success_score"], "score_status": r["score"]["score_status"]}
            safe = {key: ("'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value) for key, value in line.items()}
            writer.writerow(safe)
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=campuspulse-students.csv"})

    def find_student(student_id: str):
        frame, _ = _load(app)
        records = _records(frame)
        return next((r for r in records if str(r.get("student_id")) == student_id), None)

    @app.get("/api/students/<student_id>")
    def student_detail(student_id):
        row = find_student(student_id)
        return (jsonify(row), 200) if row else (jsonify({"error": "Student not found"}), 404)

    @app.get("/api/students/<student_id>/risk")
    def student_risk(student_id):
        row = find_student(student_id)
        return (jsonify(row["risk"]), 200) if row else (jsonify({"error": "Student not found"}), 404)

    @app.get("/api/students/<student_id>/recommendations")
    def student_recommendations(student_id):
        row = find_student(student_id)
        return (jsonify({"recommendations": recommendations_for(row)}), 200) if row else (jsonify({"error": "Student not found"}), 404)

    @app.get("/api/dashboard/summary")
    @app.get("/api/dashboard/kpis")
    def dashboard_summary():
        frame, quality = _load(app); rows = _records(frame); scores = [r["score"]["success_score"] for r in rows if r["score"]["success_score"] is not None]
        attendance_values = pd.to_numeric(frame.get("attendance_pct", pd.Series(dtype=float)), errors="coerce").dropna()
        marks_values = pd.to_numeric(frame.get("academic_marks", pd.Series(dtype=float)), errors="coerce").dropna()
        flagged = sum(r["risk"]["academic"]["category"] == "risk" or r["risk"]["placement"]["category"] == "risk" for r in rows)
        distribution = [{"range": label, "count": sum(low <= s < high for s in scores)} for label, low, high in (("0–39", 0, 40), ("40–59", 40, 60), ("60–79", 60, 80), ("80–100", 80, 101))]
        return jsonify({"student_count": len(rows), "total_students": len(rows), "average_attendance": round(float(attendance_values.mean()), 2) if len(attendance_values) else None, "average_academic_marks": round(float(marks_values.mean()), 2) if len(marks_values) else None, "high_risk_student_count": sum(r["risk_level"] == "High" for r in rows), "scored_student_count": len(scores), "mean_success_score": round(sum(scores)/len(scores), 2) if scores else None,
                        "students_with_observed_risk": flagged, "needs_assessment_count": sum("needs_assessment" in (r["risk"]["academic"]["category"], r["risk"]["placement"]["category"]) for r in rows), "score_distribution": distribution, "data_quality": quality})

    @app.get("/api/analytics/departments")
    def departments():
        frame, _ = _load(app); rows = _records(frame); grouped: dict[str, list] = {}
        for r in rows:
            grouped.setdefault(str(r.get("department") or "Unspecified"), []).append(r)
        return jsonify([{"department": k, "student_count": len(v), "mean_success_score": round(sum(s for s in (x["score"]["success_score"] for x in v) if s is not None)/len([x for x in v if x["score"]["success_score"] is not None]), 2) if any(x["score"]["success_score"] is not None for x in v) else None} for k,v in sorted(grouped.items())])

    @app.get("/api/analytics/risks")
    def risks():
        frame, _ = _load(app); rows = _records(frame)
        return jsonify({"academic": {k: sum(r["risk"]["academic"]["category"] == k for r in rows) for k in ("risk", "needs_assessment", "no_observed_flag")},
                        "placement": {k: sum(r["risk"]["placement"]["category"] == k for r in rows) for k in ("risk", "needs_assessment", "no_observed_flag")},
                        "segments": [{"name": name, "count": sum(any(s["name"] == name for s in r["segments"]) for r in rows)} for name in sorted({s["name"] for r in rows for s in r["segments"]})], "segments_overlap": True})

    @app.errorhandler(404)
    def not_found(_error): return jsonify({"error": "Not found"}), 404
    return app


app = create_app()
if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=False)
