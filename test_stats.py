"""Dependency-free tests for the analytics core.  Run: python -m unittest discover -s tests"""
import os, sys, unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import stats  # noqa: E402
from app.stats import Rec  # noqa: E402

T0 = datetime(2026, 9, 1)


def mk(job, statuses, durs, start=T0, step=timedelta(hours=6)):
    return [Rec(job, i + 1, s, d, start + i * step) for i, (s, d) in enumerate(zip(statuses, durs))]


class StatsTests(unittest.TestCase):
    def test_summary(self):
        recs = mk("a", ["SUCCESS", "SUCCESS", "FAILURE", "SUCCESS", "ABORTED"], [100, 200, 300, 400, 9999])
        s = stats.summarize(recs)
        self.assertEqual(s["total_builds"], 5)
        self.assertEqual(s["completed_builds"], 4)
        self.assertEqual((s["avg_duration_ms"], s["min_duration_ms"], s["max_duration_ms"]), (250, 100, 400))
        self.assertEqual((s["success_rate"], s["failure_rate"]), (75.0, 25.0))

    def test_empty(self):
        s = stats.summarize([])
        self.assertIsNone(s["success_rate"])
        self.assertIsNone(s["avg_duration_ms"])

    def test_slow_builds(self):
        durs = [100, 102, 98, 101, 99, 100, 103, 97, 100, 500]
        out = stats.slow_builds(mk("a", ["SUCCESS"] * 10, durs))
        self.assertEqual([b["build_number"] for b in out], [10])
        self.assertGreater(out[0]["slowdown_factor"], 3)
        # absolute threshold mode
        out = stats.slow_builds(mk("a", ["SUCCESS"] * 3, [10, 20, 30]), threshold_ms=15)
        self.assertEqual(len(out), 2)

    def test_failing_jobs(self):
        flaky = mk("flaky", ["SUCCESS", "FAILURE"] * 4, [1] * 8)
        broken = mk("broken", ["SUCCESS", "SUCCESS", "SUCCESS", "FAILURE", "FAILURE", "FAILURE"], [1] * 6)
        fine = mk("fine", ["SUCCESS"] * 8, [1] * 8)
        out = {j["job_name"]: j for j in stats.failing_jobs(flaky + broken + fine)}
        self.assertEqual(set(out), {"flaky", "broken"})
        self.assertEqual(out["flaky"]["pattern"], "flaky")
        self.assertEqual(out["broken"]["pattern"], "broken")
        self.assertEqual(out["broken"]["current_failure_streak"], 3)

    def test_trend_degrading_and_improving(self):
        up = mk("a", ["SUCCESS"] * 10, [100 + 20 * i for i in range(10)], step=timedelta(days=1))
        t = stats.trend(up)
        self.assertEqual(t["duration_trend"], "degrading")
        self.assertEqual(len(t["series"]), 10)
        down = mk("a", ["SUCCESS"] * 10, [300 - 20 * i for i in range(10)], step=timedelta(days=1))
        self.assertEqual(stats.trend(down)["duration_trend"], "improving")
        flat = mk("a", ["SUCCESS"] * 10, [100] * 10, step=timedelta(days=1))
        self.assertEqual(stats.trend(flat)["duration_trend"], "stable")

    def test_trend_success_rate_drop_and_few_points(self):
        st = ["SUCCESS"] * 6 + ["FAILURE"] * 6
        t = stats.trend(mk("a", st, [100] * 12, step=timedelta(days=1)))
        self.assertEqual(t["success_rate_trend"], "degrading")
        self.assertEqual(stats.trend(mk("a", ["SUCCESS"] * 2, [1, 1]))["duration_trend"], "insufficient_data")

    def test_weekly_bucket(self):
        recs = mk("a", ["SUCCESS"] * 14, [100] * 14, step=timedelta(days=1))
        self.assertLessEqual(len(stats.trend(recs, "week")["series"]), 3)


if __name__ == "__main__":
    unittest.main()
