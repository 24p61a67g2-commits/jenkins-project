import os
from datetime import timedelta
from contextlib import asynccontextmanager
from typing import Literal

import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud, jenkins_client, stats
from .database import Base, engine, get_db
from .models import Build
from .schemas import BuildIn, BuildOut, BulkIn, SyncIn


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Jenkins Build Analytics API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

Days = Query(None, ge=1, description="Only consider builds from the last N days")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- ingestion ----------
@app.post("/api/builds", response_model=BuildOut, status_code=201)
def add_build(build: BuildIn, db: Session = Depends(get_db)):
    crud.upsert_builds(db, [build])
    return db.scalar(select(Build).where(Build.job_name == build.job_name, Build.build_number == build.build_number))


@app.post("/api/builds/bulk")
def add_builds(body: BulkIn, db: Session = Depends(get_db)):
    return crud.upsert_builds(db, body.builds)


@app.post("/api/jenkins/sync")
def sync_from_jenkins(body: SyncIn, db: Session = Depends(get_db)):
    results = {}
    for job in body.jobs:
        try:
            results[job] = crud.upsert_builds(db, jenkins_client.fetch_builds(job, body.limit))
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        except requests.RequestException as e:
            results[job] = {"error": str(e)}
    return results


# ---------- raw data ----------
@app.get("/api/builds", response_model=list[BuildOut])
def list_builds(job: str | None = None, status: str | None = None, days: int | None = Days,
                limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db)):
    q = select(Build).order_by(Build.started_at.desc())
    if job:
        q = q.where(Build.job_name == job)
    if status:
        q = q.where(Build.status == status.upper())
    if days:
        q = q.where(Build.started_at >= crud.utcnow() - timedelta(days=days))
    return db.scalars(q.limit(limit).offset(offset)).all()


# ---------- statistics ----------
@app.get("/api/stats/summary")
def summary(job: str | None = None, days: int | None = Days, db: Session = Depends(get_db)):
    """Build count, avg/min/max duration, success & failure rate (overall or for one job)."""
    return stats.summarize(crud.fetch_recs(db, job, days))


@app.get("/api/stats/jobs")
def jobs(days: int | None = Days, db: Session = Depends(get_db)):
    """The same metrics, one row per job."""
    return stats.per_job(crud.fetch_recs(db, None, days))


# ---------- analysis ----------
@app.get("/api/analysis/slow-builds")
def slow(job: str | None = None, days: int | None = Days,
         k: float = Query(2.0, gt=0, description="stdev multiplier above the job's mean"),
         threshold_ms: int | None = Query(None, ge=1, description="absolute cut-off; overrides k"),
         limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    return stats.slow_builds(crud.fetch_recs(db, job, days), k=k, threshold_ms=threshold_ms, limit=limit)


@app.get("/api/analysis/failing-jobs")
def failing(days: int | None = Days, min_builds: int = Query(5, ge=1),
            min_failure_rate: float = Query(20.0, ge=0, le=100), db: Session = Depends(get_db)):
    return stats.failing_jobs(crud.fetch_recs(db, None, days), min_builds, min_failure_rate)


@app.get("/api/analysis/trends")
def trends(job: str | None = None, days: int = Query(30, ge=1), bucket: Literal["day", "week"] = "day",
           db: Session = Depends(get_db)):
    return stats.trend(crud.fetch_recs(db, job, days), bucket)


# ---------- one-call dashboard ----------
@app.get("/api/dashboard")
def dashboard(days: int = Query(30, ge=1), db: Session = Depends(get_db)):
    recs = crud.fetch_recs(db, None, days)
    return {
        "window_days": days,
        "summary": stats.summarize(recs),
        "jobs": stats.per_job(recs),
        "slow_builds": stats.slow_builds(recs, limit=10),
        "failing_jobs": stats.failing_jobs(recs, limit=10),
        "trend": stats.trend(recs, "day"),
    }
