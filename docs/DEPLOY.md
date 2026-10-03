# Deploying (Render free tier + Supabase)

The app is one service: the Docker image builds the React app, then runs FastAPI, which serves both the app and the API.
The database is a separate Supabase Postgres project. Nothing else is needed.

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+asyncpg://...` using Supabase's **Session pooler** string (the direct host is IPv6-only) |
| `APIFY_TOKEN` | yes | public scraping through Apify actors |
| `GEMINI_API_KEY` | yes | the project behind the key should have billing set up if you want more than the free quota; the code stops paid calls at a dollar ceiling |
| `GROQ_API_KEY` | yes | free tier is fine; it is the fallback and the first choice for date turns |
| `PASTE_ENABLED` | no | `false` is a kill switch for new runs while the demo stays browsable (default `true`) |
| `LIVE_RUN_DAILY_CAP` | no | live runs per day (default 12; the counter is in memory and resets on restart) |

Secrets are only ever environment variables. `.env` is gitignored; `.env.example` lists the names.

## One-time setup

1. Create a Supabase project and run `python -m scripts.init_db` once from a machine that has `DATABASE_URL` set. It creates the
   11 tables and turns row-level security on with no policies.
2. Seed and run the pool from a laptop (the long job does not belong on a free web instance):
   `python -m scripts.seed_pool pool.csv --ingest`, then `python -m scripts.run_demo25`, then `python -m scripts.run_demo25 --publish`.
   `pool.csv` has the columns `linkedin_url, instagram_url, consent`; it is gitignored on purpose.

## Render

`render.yaml` is a Blueprint for one Docker web service on the free plan, in the Singapore region (next to the Supabase project, which keeps
query latency low). Either create it from the Blueprint, or create a web service by hand pointing at the repo with runtime Docker, then add
the four secrets in the dashboard under Environment.

Free-tier behaviour to plan for:

- The instance **sleeps after about 15 idle minutes** and takes about a minute to wake. Open it once before a demo, or point a free uptime
  pinger at `/health` every 10 minutes.
- On start-up the app pre-computes every page of the published demo in the background (a few minutes), so the first visitors after a wake may
  see slower pages until it finishes.
- The instance has about 512 MB of memory. The pre-computed demo is a few megabytes, and the app runs a single worker.
- Do not redeploy while a live run is in progress; runs are database-backed but the in-flight job is a process-local task.

## Checks after deploying

1. `GET /health` returns `{"ok": true}`.
2. `GET /api/config` shows the demo's token and `paste_enabled: true`.
3. Open the demo, a profile, a transcript, the grid and the rankings.
4. Paste one test person with the demo option on and watch it finish (about 5 minutes, about $0.20), then delete them from the "About the results" tab.

Known unverified: the container build itself was not run locally (Docker was unavailable), so the first Render build is the first real test of the `Dockerfile`.
