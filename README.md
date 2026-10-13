# CampusPulse

CampusPulse is a student hackathon prototype for explainable student support analytics. It joins local CSV sources, calculates a configurable coverage-aware success score, raises independent academic and placement review flags, and suggests staff-reviewed support actions. It is a rule-based decision-support prototype, not a validated prediction of student outcomes.

## Current data setup

Place institution-approved CSVs in `backend/data/`. The application expects `students.csv` as its roster and optionally reads `academics.csv`, `attendance.csv`, `lms.csv`, `engagement.csv`, `placement.csv`, `skills.csv`, and `skills_feedback.csv`. Every source must have a unique, nonblank `student_id`; optional sources with invalid IDs are excluded and reported. The roster is preserved with left joins. Missing optional sources or measurements stay missing. **The repository includes a fictional 10-student CSE AIML demo roster** in `backend/data/students.csv`. It is intended for hackathon demonstration only; replace it only with authorized data when appropriate.

Recognized indicator headers are documented in [docs/methodology.md](docs/methodology.md). Only the student identifier is required for integration; measurements are optional and included in scoring only when valid. The included demo roster contains synthetic student data.

## Windows PowerShell setup

Run commands from the repository root:

```powershell
# Create and activate a virtual environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install backend packages
python -m pip install -r backend\requirements.txt

# Start Flask API (keep this terminal open)
python backend\main.py
# Health check: http://127.0.0.1:5000/api/health

# In a second terminal, install and start the frontend
cd frontend
npm install
npm run dev

# Backend tests (from repository root)
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests -q

# Frontend production build (from frontend directory)
npm run build
```

The Vite development server proxies `/api` to `http://127.0.0.1:5000`. Set `VITE_API_BASE_URL` when serving the frontend separately. Set `CAMPUSPULSE_CORS_ORIGINS` to a comma-separated list of permitted frontend origins when a proxy is not used. `CAMPUSPULSE_DATA_DIR` may point to a different data directory.

## API routes

`/api/health`, `/api/methodology`, `/api/data-quality`, `/api/filters`, `/api/dashboard/summary`, `/api/dashboard/kpis`, `/api/students`, `/api/students/<student_id>`, `/api/students/<student_id>/risk`, `/api/students/<student_id>/recommendations`, `/api/analytics/departments`, `/api/analytics/risks`, and `/api/students/export`.

Student listing supports `department`, `year`, `search`, `academic_risk`, `placement_risk`, `overall_risk`, `risk_only`, `page`, and `per_page` query parameters.

## Troubleshooting

- **CSV not detected:** confirm the exact lowercase filename under `backend/data/`, especially `attendance.csv` (singular), and restart Flask.
- **Missing or duplicate IDs:** every source must have a nonblank, unique `student_id`; inspect `/api/data-quality` for source details.
- **Python command not found:** install Python with the Windows launcher (`py`) and recreate `.venv`.
- **Vite cannot connect:** confirm Flask is running on port 5000 and open the Vite URL (usually `http://localhost:5173`).
- **CORS errors:** use the Vite proxy or configure `CAMPUSPULSE_CORS_ORIGINS` with the exact frontend origin.
- **No values in dashboard:** check `/api/data-quality`; the API reports missing or invalid roster data instead of presenting fabricated zero values.

## Demo and limitations

Follow [docs/demo-script.md](docs/demo-script.md) for the demo. Prototype weights, thresholds, indicator scales, and support rules require institution review. No predictive model has been trained. Verify source definitions and student privacy controls before any real deployment.

For a public HTTPS deployment, follow [docs/deployment.md](docs/deployment.md). The included Render Blueprint targets the existing Flask API; deploy the existing Vite frontend as a Render Static Site from the `frontend/` root and set `VITE_API_BASE_URL` to the actual API HTTPS origin.

## Complete demonstration sources and scoring

All eight CSV source files are present in `backend/data/`. The ten roster IDs are reused by seven supplemental files. Every row is synthetic demonstration data, not an institutional record. The supplementary schemas and join key are listed in [docs/methodology.md](docs/methodology.md).

Prototype score weights are academics 30%, attendance 20%, LMS 15%, placement readiness 20%, skills and engagement 10%, and support feedback 5%. Coverage is the sum of weights for components with valid measurements. Those component weights are renormalized only when coverage reaches 70%; below that threshold the numeric score is null. Scores below full coverage are provisional.

Hosted URLs supplied for the project: [frontend](https://smart-campus-analytics-e04c.onrender.com) · [backend API](https://campuspulse-api-srj8.onrender.com). These links do not imply that a deployment was performed as part of this work.
