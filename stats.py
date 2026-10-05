"""Pure analytics (no DB / framework imports) so it is easy to unit-test.

Conventions
- ABORTED / NOT_BUILT builds are excluded from rates and durations (they say nothing
  about code health or speed) but are still counted in `total_builds`.
- Rates are percentages of *completed* builds (SUCCESS + FAILURE + UNSTABLE).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, stdev

COMPLETED = {"SUCCESS", "FAILURE", "UNSTABLE"}


@dataclass(frozen=True)
class Rec:
    job: str
    number: int
    status: str
    duration_ms: int
    started_at: datetime


def _pct(a: int, b: int):
    return round(100 * a / b, 2) if b else None


def _completed(recs):
    return [r for r in recs if r.status in COMPLETED]


def summarize(recs) -> dict:
    done = _completed(recs)
    n = len(done)
    ok = sum(r.status == "SUCCESS" for r in done)
    bad = sum(r.status == "FAILURE" for r in done)
    unstable = sum(r.status == "UNSTABLE" for r in done)
    d = [r.duration_ms for r in done]
    return {
        "total_builds": len(recs),
        "completed_builds": n,
        "success_count": ok,
        "failure_count": bad,
        "unstable_count": unstable,
        "success_rate": _pct(ok, n),
        "failure_rate": _pct(bad, n),
        "avg_duration_ms": round(mean(d)) if d else None,
        "min_duration_ms": min(d) if d else None,
        "max_duration_ms": max(d) if d else None,
    }


def _by_job(recs):
    g = defaultdict(list)
    for r in recs:
        g[r.job].append(r)
    for v in g.values():
        v.sort(key=lambda r: (r.started_at, r.number))
    return g


def per_job(recs) -> list[dict]:
    return [{"job_name": j, **summarize(v)} for j, v in sorted(_by_job(recs).items())]


def slow_builds(recs, k: float = 2.0, min_samples: int = 5, threshold_ms: int | None = None, limit: int = 50):
    """Flag builds slower than the job's own baseline: duration > mean + k * stdev.
    If threshold_ms is given it is used as an absolute cut-off for every job instead."""
    out = []
    for job, v in _by_job(_completed(recs)).items():
        d = [r.duration_ms for r in v]
        if threshold_ms is None and len(d) < min_samples:
            continue
        m = mean(d)
        sd = stdev(d) if len(d) > 1 else 0.0
        cut = threshold_ms if threshold_ms is not None else m + k * sd
        for r in v:
            if r.duration_ms > cut:
                out.append({
                    "job_name": job, "build_number": r.number, "status": r.status,
                    "started_at": r.started_at.isoformat(), "duration_ms": r.duration_ms,
                    "job_avg_ms": round(m), "threshold_ms": round(cut),
                    "slowdown_factor": round(r.duration_ms / m, 2) if m else None,
                    "z_score": round((r.duration_ms - m) / sd, 2) if sd else None,
                })
    out.sort(key=lambda x: x["slowdown_factor"] or 0, reverse=True)
    return out[:limit]


def failing_jobs(recs, min_builds: int = 5, min_failure_rate: float = 20.0, limit: int = 50):
    out = []
    for job, v in _by_job(_completed(recs)).items():
        if len(v) < min_builds:
            continue
        st = [r.status for r in v]
        fails = st.count("FAILURE")
        rate = _pct(fails, len(st))
        if rate < min_failure_rate:
            continue
        streak = 0
        for s in reversed(st):
            if s != "FAILURE":
                break
            streak += 1
        flips = sum(1 for a, b in zip(st, st[1:]) if {a, b} == {"SUCCESS", "FAILURE"})
        pattern = "broken" if streak >= 3 else "flaky" if flips >= 3 else "frequent_failures"
        last_fail = max(r.started_at for r in v if r.status == "FAILURE")
        out.append({
            "job_name": job, "completed_builds": len(st), "failure_count": fails,
            "failure_rate": rate, "current_failure_streak": streak,
            "status_flips": flips, "pattern": pattern,
            "last_failure_at": last_fail.isoformat(),
        })
    out.sort(key=lambda x: (x["failure_rate"], x["current_failure_streak"]), reverse=True)
    return out[:limit]


def _slope(ys):
    n = len(ys)
    mx, my = (n - 1) / 2, sum(ys) / n
    den = sum((x - mx) ** 2 for x in range(n))
    return sum((x - mx) * (y - my) for x, y in enumerate(ys)) / den if den else 0.0


def _bucket(dt: datetime, bucket: str) -> str:
    d = dt.date()
    if bucket == "week":
        d = d - timedelta(days=d.weekday())  # Monday of that week
    return d.isoformat()


def trend(recs, bucket: str = "day") -> dict:
    """Time series + linear-regression direction for duration and success rate."""
    groups = defaultdict(list)
    for r in _completed(recs):
        groups[_bucket(r.started_at, bucket)].append(r)
    series = []
    for period in sorted(groups):
        s = summarize(groups[period])
        series.append({"period": period, "builds": s["completed_builds"],
                       "avg_duration_ms": s["avg_duration_ms"], "success_rate": s["success_rate"]})

    result = {"bucket": bucket, "series": series,
              "duration_trend": "insufficient_data", "duration_change_pct": None,
              "success_rate_trend": "insufficient_data", "success_rate_change_pts": None}
    if len(series) < 3:
        return result

    durs = [p["avg_duration_ms"] for p in series]
    chg = _slope(durs) * (len(durs) - 1) / mean(durs) * 100  # fitted % change over the window
    result["duration_change_pct"] = round(chg, 1)
    result["duration_trend"] = "degrading" if chg > 10 else "improving" if chg < -10 else "stable"

    rates = [p["success_rate"] for p in series]
    pts = _slope(rates) * (len(rates) - 1)  # fitted change in percentage points
    result["success_rate_change_pts"] = round(pts, 1)
    result["success_rate_trend"] = "improving" if pts > 5 else "degrading" if pts < -5 else "stable"
    return result
