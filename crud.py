from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Build
from .schemas import BuildIn
from .stats import Rec


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upsert_builds(db: Session, items: list[BuildIn]) -> dict:
    """Insert new builds, update existing ones (unique on job_name + build_number)."""
    inserted = updated = 0
    by_job = defaultdict(list)
    for it in items:
        by_job[it.job_name].append(it)

    for job, its in by_job.items():
        nums = [i.build_number for i in its]
        existing = {}
        for i in range(0, len(nums), 500):  # chunk to stay under DB bind-variable limits
            rows = db.scalars(select(Build).where(Build.job_name == job, Build.build_number.in_(nums[i:i + 500])))
            existing.update({b.build_number: b for b in rows})
        for it in its:
            row = existing.get(it.build_number)
            if row:
                for f, v in it.model_dump().items():
                    setattr(row, f, v)
                updated += 1
            else:
                row = Build(**it.model_dump())
                db.add(row)
                existing[it.build_number] = row
                inserted += 1
    db.commit()
    return {"inserted": inserted, "updated": updated}


def fetch_recs(db: Session, job: str | None = None, days: int | None = None) -> list[Rec]:
    q = select(Build.job_name, Build.build_number, Build.status, Build.duration_ms, Build.started_at)
    if job:
        q = q.where(Build.job_name == job)
    if days:
        q = q.where(Build.started_at >= utcnow() - timedelta(days=days))
    return [Rec(*row) for row in db.execute(q)]
