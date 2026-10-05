"""Generate ~45 days of synthetic Jenkins builds so the dashboard has data.  Run: python seed.py"""
import random
from datetime import timedelta

from app import crud
from app.database import Base, SessionLocal, engine
from app.schemas import BuildIn

random.seed(42)
DAYS = 45
# job: (base duration s, fail prob, duration drift per day s, outlier prob)
JOBS = {
    "api-service":     (240, 0.03, 0, 0.02),
    "web-frontend":    (180, 0.05, 4, 0.01),   # gets steadily slower
    "payment-service": (300, 0.35, 0, 0.02),   # flaky
    "data-pipeline":   (600, 0.08, 0, 0.08),   # occasional very slow runs
    "docs-site":       (60,  0.02, 0, 0.0),
}


def main():
    Base.metadata.create_all(engine)
    now = crud.utcnow()
    items = []
    for job, (base, p_fail, drift, p_slow) in JOBS.items():
        n = 0
        for day in range(DAYS, 0, -1):
            for _ in range(random.randint(3, 6)):
                n += 1
                t = now - timedelta(days=day, hours=random.randint(0, 23), minutes=random.randint(0, 59))
                dur = max(5, random.gauss(base + drift * (DAYS - day), base * 0.08))
                if random.random() < p_slow:
                    dur *= random.uniform(2.5, 4)
                r = random.random()
                status = "FAILURE" if r < p_fail else "UNSTABLE" if r < p_fail + 0.02 else "SUCCESS"
                items.append(BuildIn(job_name=job, build_number=n, status=status,
                                     duration_ms=int(dur * 1000), started_at=t))
        # make the last builds of one job a hard failure streak
        if job == "docs-site":
            for it in items[-4:]:
                it.status = "FAILURE"
    with SessionLocal() as db:
        print(crud.upsert_builds(db, items))


if __name__ == "__main__":
    main()
