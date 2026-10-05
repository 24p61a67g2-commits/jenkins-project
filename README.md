# Jenkins Build Analytics Backend (Python · FastAPI · SQLAlchemy)

Stores Jenkins build history in a database and exposes analytics APIs for a dashboard.

## Run
```bash
pip install -r requirements.txt
python seed.py                         # optional: 45 days of demo data
uvicorn app.main:app --reload          # docs at http://localhost:8000/docs
python -m unittest discover -s tests   # analytics unit tests (no dependencies needed)
```
Config (env vars): `DATABASE_URL` (default SQLite `jenkins.db`; PostgreSQL works via `postgresql+psycopg2://...`),
`JENKINS_URL`, `JENKINS_USER`, `JENKINS_API_TOKEN`, `CORS_ORIGINS`.

## Data model — table `builds`
`id, job_name, build_number, status, duration_ms, started_at (UTC), url, triggered_by` — unique on `(job_name, build_number)`, so re-ingesting is safe (upsert).

## API
| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/builds` | Store one build (webhook / Jenkins post-build step) |
| POST | `/api/builds/bulk` | Store up to 5000 builds |
| POST | `/api/jenkins/sync` | Pull history from Jenkins: `{"jobs":["api-service"],"limit":100}` |
| GET | `/api/builds` | List builds (`job, status, days, limit, offset`) |
| GET | `/api/stats/summary` | Count, avg/min/max duration, success & failure rate (`job, days`) |
| GET | `/api/stats/jobs` | Same metrics per job |
| GET | `/api/analysis/slow-builds` | Builds slower than `mean + k·stdev` of their job (`k=2`), or above `threshold_ms` |
| GET | `/api/analysis/failing-jobs` | Jobs with failure rate ≥ `min_failure_rate`%; labelled `broken` / `flaky` / `frequent_failures` |
| GET | `/api/analysis/trends` | Per-day/week series + `degrading/stable/improving` for duration and success rate |
| GET | `/api/dashboard` | Everything above in one call (`days=30`) |

Examples:
```bash
curl "localhost:8000/api/stats/summary?days=30"
curl "localhost:8000/api/analysis/trends?job=web-frontend&bucket=week"
curl -X POST localhost:8000/api/builds -H 'content-type: application/json' \
  -d '{"job_name":"api-service","build_number":501,"status":"SUCCESS","duration_ms":241000,"started_at":"2026-10-05T09:30:00Z"}'
```
To push from Jenkins itself, add a post-build `curl` to `/api/builds` using `$JOB_NAME`, `$BUILD_NUMBER`, `currentBuild.result`, `currentBuild.duration`.

## Metric definitions
- Rates are % of *completed* builds (SUCCESS + FAILURE + UNSTABLE); ABORTED/NOT_BUILT are excluded from rates and durations.
- Trend = least-squares line through the bucketed averages. Duration: >+10% fitted change over the window = degrading, <-10% = improving. Success rate: ±5 percentage points. Fewer than 3 buckets = `insufficient_data`.
- Failing-job pattern: `broken` = last 3+ builds failed; `flaky` = 3+ SUCCESS↔FAILURE flips.

## Layout
`app/stats.py` pure analytics · `app/crud.py` DB access/upsert · `app/main.py` routes · `app/jenkins_client.py` Jenkins API · `app/models.py`, `schemas.py`, `database.py`
