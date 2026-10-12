# Public deployment handoff

## Current workspace check

CampusPulse is a Vite/React frontend in `frontend/` and a Flask API in `backend/main.py`. The frontend reads `VITE_API_BASE_URL`; the backend reads `CAMPUSPULSE_CORS_ORIGINS` and an optional `CAMPUSPULSE_DATA_DIR`. Its default CSV location is the repository-relative `backend/data/`, not a Windows absolute path. No `backend/data/` directory or CSV files currently exist in the inspected workspace. No `.git` directory or Git remote is configured. Do not expect student rows in the public deployment until the authorized CSVs are added to the repository.

## Hosting choice

Use **Render Web Service** for Flask and **Vercel** for the static Vite app. `render.yaml` installs Gunicorn, starts the existing Flask `app`, and sets `/api/health` as the service health check. Vercel can detect the Vite app when its project Root Directory is set to `frontend`; its build output is `dist`.

The free Render web service sleeps after 15 minutes without traffic, takes about a minute to wake, and has an ephemeral filesystem. The tracked CSV files must therefore be included in Git at deploy time; do not upload them to the service filesystem manually. Render says its free tier is intended for hobby/testing rather than production. Vercel's free Hobby plan is for personal, non-commercial use, so check that its terms fit this hackathon/submission use; otherwise choose a Vercel paid plan or another static host. See the provider docs linked below.

## One-time account and repository setup

This machine has no Git repository/remote and no connected GitHub, Render, or Vercel account tool. Create a **private GitHub repository** from this workspace through GitHub Desktop or the GitHub website, then push the project files. Keep real student CSVs out of a public repository; only push them to a private repository if you have authorization and the institution permits that processing. Check repository access granted to the hosting providers.

## Deploy the backend first

1. Sign in to Render and select **New → Blueprint** (or **New → Web Service**).
2. Connect the GitHub repository containing this project. For a Blueprint, select the root-level `render.yaml` and create the `campuspulse-api` service.
3. When asked for `CAMPUSPULSE_CORS_ORIGINS`, temporarily enter `http://localhost:5173` to let the API deploy. This temporary value does not authorize the eventual frontend; it must be replaced in the next steps.
4. Wait for Render's deploy status to become **Live**. Copy the actual service HTTPS origin shown by Render (for example, copy the URL from the dashboard; do not assume the name-derived URL is available).
5. Check `<copied-render-origin>/api/health`. It should return JSON with `"status":"ok"`.

The service executes from the checked-out repository and discovers CSVs at `backend/data/`; `CAMPUSPULSE_DATA_DIR` can override this with a path inside the deployed checkout. Do not set it to a Windows path. Re-deploy after adding or changing repository CSV files. The current repository contains no such CSVs.

## Deploy the frontend

1. In Vercel, choose **Add New → Project**, import the same GitHub repository, and set **Root Directory** to `frontend`.
2. Confirm Vercel uses `npm install`/`npm ci`, `npm run build`, and output directory `dist` (the Vite defaults).
3. Add `VITE_API_BASE_URL` for the **Production** environment. Its value is the exact Render HTTPS origin copied above, without a trailing slash (for example, `https://<actual-service-host>`).
4. Deploy. Copy the actual production HTTPS domain that Vercel assigns.

Vite embeds `VITE_API_BASE_URL` during build; changing it requires a new deployment.

## Finish CORS and verify

1. In Render, open the API service's **Environment** settings and set `CAMPUSPULSE_CORS_ORIGINS` to the exact Vercel production origin, including `https://` and without a trailing slash. To allow Vercel preview deployments too, add only their exact origins as a comma-separated list; avoid `*`.
2. Save changes and wait for the Render service to redeploy.
3. Open the Vercel production URL over HTTPS. In browser Developer Tools → Network, verify `/api/dashboard/summary`, `/api/analytics/risks`, `/api/analytics/departments`, `/api/filters`, and `/api/students` return successfully from the Render origin. With no CSVs in the repository, the student list should be empty; health and quality routes should still work.
4. Record the actual URLs from provider dashboards and repeat both the API health check and frontend network check after every deployment.

## Provider references and current free-plan limits

- [Render Flask deployment](https://render.com/docs/deploy-flask)
- [Render Blueprints](https://render.com/docs/blueprint-spec)
- [Render free instance limits](https://render.com/docs/free)
- [Render Python version selection](https://render.com/docs/python-version)
- [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite)
- [Vercel project build configuration](https://vercel.com/docs/builds/configure-a-build)
- [Vercel Hobby plan terms and quotas](https://vercel.com/docs/plans/hobby)
