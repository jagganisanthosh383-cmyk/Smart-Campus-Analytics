# Render deployment handoff

CampusPulse already has a Flask API configured in the root `render.yaml` and a Vite/React app under `frontend/`. The demo roster is `backend/data/students.csv`; the backend resolves it relative to its Python module, so the CSV ships with the repository checkout. This workspace has the GitHub remote `https://github.com/jagganisanthosh383-cmyk/Smart-Campus-Analytics` configured. Local edits must be pushed to the connected branch before Render can deploy them; no deployment is performed by this guide.

## Deploy or redeploy the API

1. In the Render dashboard, open the existing `campuspulse-api` Web Service connected to the repository. If it does not exist, choose **New > Blueprint** and select the root `render.yaml`.
2. Keep the existing commands: build `python -m pip install -r backend/requirements.txt`; start `python -m gunicorn --chdir backend main:app --bind 0.0.0.0:$PORT`; health check `/api/health`.
3. After pushing the changes to the configured branch, choose **Manual Deploy > Deploy latest commit** (or wait for auto-deploy).
4. Keep the generated API origin shown in the dashboard. The known API origin supplied for this project is `https://campuspulse-api-srj8.onrender.com`; verify its health at `https://campuspulse-api-srj8.onrender.com/api/health` after deployment.

## Deploy the React frontend as a Render Static Site

1. In Render, choose **New > Static Site** and connect the same GitHub repository and branch.
2. Set **Root Directory** to `frontend`.
3. Set **Build Command** to `npm install && npm run build` and **Publish Directory** to `dist`.
4. Add the build-time environment variable `VITE_API_BASE_URL=https://campuspulse-api-srj8.onrender.com`, then create the site. Vite embeds this value into the frontend bundle, so changes require a redeploy.
5. Copy the actual HTTPS `onrender.com` origin assigned to the static site from its dashboard; do not guess it.

## Connect CORS and verify

1. In the API Web Service's **Environment** settings, set `CAMPUSPULSE_CORS_ORIGINS` to the exact frontend origin from the Static Site dashboard, including `https://` and without a trailing slash. Add any explicitly used preview origins as comma-separated exact origins; do not use `*`.
2. Save and redeploy the API after changing the environment variable.
3. Verify the API health URL above, then open the frontend HTTPS URL and confirm the student roster and summary cards load. In browser Developer Tools > Network, check `/api/dashboard/summary`, `/api/analytics/risks`, `/api/analytics/departments`, `/api/filters`, and `/api/students`.

For local development, leave `VITE_API_BASE_URL` unset or blank so Vite proxies `/api` to the local Flask API. The example file `frontend/.env.example` shows both settings.

## Render plan notes

Render static sites are free and served over its CDN. Free Render web services sleep after 15 minutes without traffic, take about a minute to wake, and have an ephemeral filesystem; tracked CSV files remain available because they are part of the checked-out repository. Render describes free services as intended for testing/hobby use and advises against production use. Review current limits before submission: [Render Static Sites](https://render.com/docs/static-sites), [Render free services and limits](https://render.com/docs/free), [Render environment variables](https://render.com/docs/configure-environment-variables), and [Render Flask deployment](https://render.com/docs/deploy-flask).
