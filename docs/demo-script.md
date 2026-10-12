# CampusPulse 3–5 minute demo

1. **Problem (30 sec):** Student support information is split across academics, attendance, LMS activity, engagement, placement preparation, skills, and feedback.
2. **Integration (30 sec):** Show `backend/data/` and `/api/data-quality`. Explain the roster-based left joins, the `attendance.csv` filename, duplicate/orphan checks, and how missing records stay missing. If institutional data is not available, demonstrate the empty-data state; do not invent student measurements.
3. **Dashboard (45 sec):** Review roster and score coverage KPIs. Explain that the score requires 70% component-weight coverage and partial scores are provisional. Use charts only when real source rows exist.
4. **Find students for support (45 sec):** Search/filter by department and year; enable the risk/assessment filter. Emphasize that missing assessments are surfaced separately from observed risk flags.
5. **Profile and action (60 sec):** Open a student profile. Explain component evidence, independent academic and placement risk rules, and reviewable recommendations. Clarify that the app does not claim an intervention is complete.
6. **Method and data quality (45 sec):** Show score weights, threshold examples, source quality, and export. Describe coverage and source limitations.
7. **Close (30 sec):** Explain that this is a rule-based prototype. Next steps are validating schemas and thresholds with the institution, privacy/access review, outcome-based evaluation, and only then considering a validated predictive model.

## Slide outline

1. Fragmented student-support data and the campus problem
2. CampusPulse workflow and staff/student impact
3. Architecture: CSV inputs → Python/pandas integration → Flask scoring/API → React dashboard
4. Transparent score, coverage policy, and independent risk rules
5. Demonstration insights and support segments (use approved real data)
6. Limitations: data quality, prototype thresholds, no validated ML model
7. Future scope: institutional validation, privacy/access controls, intervention tracking, outcome evaluation
