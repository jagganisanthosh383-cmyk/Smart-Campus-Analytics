# CampusPulse methodology

## Data sources and schema

The roster is `backend/data/students.csv`, keyed by unique `student_id`. Optional files are `academics.csv`, `attendance.csv`, `lms.csv`, `engagement.csv`, `placement.csv`, `skills.csv`, and `skills_feedback.csv`. The attendance filename is **`attendance.csv`**. A source is joined one-to-one by ID; optional sources are left-joined to preserve every roster student. Duplicate, blank-ID, unreadable, or structurally invalid optional sources are reported and not integrated. Orphan IDs (present in an optional file but not in the roster) are counted and excluded. Student IDs are read as strings and trimmed.

Each source must include `student_id`. The roster `students.csv` is required to calculate student-level results; optional academic, attendance, LMS, engagement, placement, skills, and feedback source files are left-joined only when present. Recognized indicator headers are:

| Area | Accepted headers (first matching nonmissing value) | Valid range |
|---|---|---|
| Academics | `academic_marks` (0-100), or `cgpa`, `current_cgpa`, `gpa` (0-10) |
| Attendance | `attendance_pct`, `attendance_percentage`, `attendance` | 0–100 |
| LMS | `lms_activity_score` (0-100), or assignment-completion aliases |
| Placement | `placement_readiness_score` (0-100), or aptitude, coding, and interview assessment aliases |
| Skills and engagement | `skills_score` (0-100), or technical, soft-skill, and engagement aliases |
| Feedback | `support_feedback_score`, `skills_feedback_score`, `feedback_score` | 0–5 if value ≤5, otherwise 0–100 |

The feedback scale rule is a prototype convenience and must be confirmed against source documentation. Values outside configured ranges are treated as unavailable for scoring, not clamped. Missing sources, missing IDs, duplicate IDs, invalid numeric values (where a range is defined), rows missing from optional sources, orphan IDs, row counts, columns, and parse failures appear in `/api/data-quality`.

## Score

`backend/scoring.py` computes a transparent weighted score:

| Component | Weight | Formula |
|---|---:|---|
| Academic performance | 30% | Academic marks / 100, or legacy CGPA / 10, scaled to 100 |
| Attendance | 20% | Valid attendance percentage |
| LMS | 15% | Documented LMS activity score or assignment completion, scaled 0-100 |
| Placement readiness | 20% | Placement readiness score, or mean of available aptitude, coding, and interview scores |
| Skills and engagement | 10% | Skills score, or mean of available skills and documented engagement scores |
| Support feedback | 5% | Linear normalization from its documented 0–5 or 0–100 scale |

Coverage is the sum of the weights for components with valid measurements. Weights are renormalized over available components only when coverage is at least 70%. Below 70%, score is `null`. Scores below full coverage are marked provisional. Trend calculations are omitted because no comparable time-period schema exists in this workspace. Backlogs contribute to risk/support rules, not the score, until a defensible normalization is validated.

## Risks and segments

Academic and placement domains are evaluated independently. Example review thresholds are attendance below 65%, academic marks below 60/100 (or legacy CGPA below 6/10), assignment completion below 50%, any recorded backlog, and placement readiness or assessment below 40/100. One observed trigger yields moderate severity; multiple triggers yield high severity. If a domain has no usable indicators it returns `needs_assessment`, never a low-risk result. Thresholds are configurable in code and are examples requiring institutional validation.

Rule-based overlapping segments include strong academics with lower placement readiness, low attendance plus incomplete coursework, insufficient assessment data, academic flags needing a faculty check-in, and high academic plus placement readiness. Segment counts can overlap and must not be summed as unique students.

## Recommendations

Recommendations are tied to observed indicators such as attendance, academic marks, CGPA/backlogs, LMS activity, assignment completion, placement readiness, coding, aptitude, and interview scores. Missing assessment information prompts collection or verification. The API does not record completion of actions. Staff must review recommendations and discuss them with the student.

## Assumptions and limitations

Weights and thresholds are hackathon prototype choices, not official KPMG methodology. Available indicator headers and scales must be reconciled with institutional data dictionaries. The score describes observed data coverage and configured rules; it is not a calibrated probability of success, failure, retention, or placement. No labelled outcome data or validated predictive model exists here. Human review is required, and the system should not be used for punitive decisions.

## Demo source schemas and relationships

All source files use unique `student_id` text keys that match the ten synthetic IDs in `students.csv`. The files are joined one-to-one onto that roster; unmatched IDs are reported and not added to the roster. Supplemental rows in this repository are synthetic demonstration data.

| File | Measurement columns | Purpose |
|---|---|---|
| `students.csv` | Existing roster fields | Student demo roster and dashboard baseline indicators |
| `academics.csv` | `cgpa`, `academic_marks` | Academic performance (0-10 and 0-100) |
| `attendance.csv` | `attendance_pct` | Attendance (0-100) |
| `lms.csv` | `lms_activity_score`, `assignment_completion_pct` | LMS activity and completion (0-100) |
| `engagement.csv` | `engagement_score` | Engagement (0-100) |
| `placement.csv` | `aptitude_score`, `coding_score`, `mock_interview_score` | Placement assessment (0-100) |
| `skills.csv` | `technical_skills_score`, `soft_skills_score` | Skills assessment (0-100) |
| `skills_feedback.csv` | `support_feedback_score` | Support feedback (0-5 in the demo; confirm real source scale) |

`/api/data-quality` and `/api/methodology` report expected, valid, missing, and invalid sources. A present file with missing required columns, unreadable CSV content, or blank/duplicate IDs is invalid and excluded from joins. Measurement values outside recognized ranges are reported and treated as unavailable by score components; they are never changed to zero.

## Run and verify

From the project root, follow the Windows PowerShell setup and test commands in the README. The local suite is `\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests -q`; build the frontend from `frontend` using `npm run build`. To confirm the bundled demo source set, start the API and read `/api/data-quality`: `expected_source_count` and `detected_source_count` should both be 8, and `missing_sources` / `invalid_sources` should be empty. The UI should show `8/8 expected CSV sources valid`.

The prototype is rule-based and does not predict academic failure. Risk thresholds are examples requiring institutional validation. Missing information alone is not a high-risk signal, and recommendations require staff review. Synthetic data must not be represented as real student records.
