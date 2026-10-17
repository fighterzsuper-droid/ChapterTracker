"""Unit tests for the server's conservative study-time accounting.

Run from repository root: python -m unittest discover -s tests -v
"""
import tempfile
import time
import unittest
from pathlib import Path

from flask import Flask
import study_time as tracking
from watcher import watcher


class StudyTimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = tracking.DB
        tracking.DB = Path(self.temp.name) / "study_time.db"
        tracking.initialize()
        self.app = Flask(__name__)
        self.app.register_blueprint(tracking.study_time)
        self.app.register_blueprint(watcher)
        self.client = self.app.test_client()

    def tearDown(self):
        tracking.DB = self.original_db
        self.temp.cleanup()

    def post(self, token="a" * 32, seq=1, active=True, subject="AA"):
        response = self.client.post("/api/study-time/pulse", json={
            "tab_id": token, "seq": seq, "active": active, "subject": subject
        })
        self.assertEqual(response.status_code, 200, response.data)
        return response.get_json()

    def age_lease(self, seconds):
        with tracking.connect() as db:
            db.execute(
                "UPDATE study_lease SET last_seen=? WHERE id=1",
                (time.time() - seconds,),
            )

    def test_visible_time_counts_without_user_interaction(self):
        self.post(seq=1)
        self.age_lease(9)
        data = self.post(seq=2)
        self.assertGreaterEqual(data["today_seconds"], 8)
        self.assertLess(data["today_seconds"], 11)
        self.assertEqual(data["subject"], "AA")

    def test_hidden_tab_stops_and_does_not_count_stale_gap(self):
        self.post(seq=1)
        self.age_lease(9)
        total = self.post(seq=2, active=False)["total_seconds"]
        self.assertGreaterEqual(total, 8)
        with tracking.connect() as db:
            self.assertIsNone(db.execute("SELECT * FROM study_lease").fetchone())
        self.assertEqual(self.post(seq=3, active=False)["total_seconds"], total)

    def test_long_sleep_gap_never_counts(self):
        self.post(seq=1)
        self.age_lease(70)
        data = self.post(seq=2)
        self.assertEqual(data["total_seconds"], 0)

    def test_old_tab_cannot_stop_new_tab(self):
        self.post(token="a" * 32, seq=1)
        self.post(token="b" * 32, seq=1)
        self.post(token="a" * 32, seq=2, active=False)
        with tracking.connect() as db:
            self.assertEqual(db.execute("SELECT tab_id FROM study_lease").fetchone()[0], "b" * 32)

    def test_replayed_old_event_does_not_resurrect_timer(self):
        self.post(seq=1)
        self.post(seq=3, active=False)
        old = self.post(seq=2, active=True)
        self.assertFalse(old["accepted"])
        with tracking.connect() as db:
            self.assertIsNone(db.execute("SELECT * FROM study_lease").fetchone())

    def test_subject_totals_are_separate(self):
        self.post(subject="AA", seq=1)
        self.age_lease(9)
        self.post(subject="AA", seq=2, active=False)
        self.post(subject="TX", seq=3)
        self.age_lease(6)
        tx = self.post(subject="TX", seq=4, active=False)
        aa = self.client.get("/api/study-time/stats?subject=AA").get_json()
        self.assertGreaterEqual(aa["today_seconds"], 8)
        self.assertGreaterEqual(tx["today_seconds"], 5)
        self.assertLess(tx["today_seconds"], aa["today_seconds"])


    def test_hourly_split_at_local_hour(self):
        from datetime import datetime
        first = datetime(2026, 10, 17, 11, 59, 55, tzinfo=tracking.ZONE).timestamp()
        with tracking.connect() as db:
            tracking.add_seconds(db, "AA", first, first + 10)
            buckets = db.execute(
                "SELECT hour,seconds FROM study_hour WHERE subject='AA' ORDER BY hour"
            ).fetchall()
            total = db.execute(
                "SELECT SUM(seconds) FROM study_day WHERE subject='AA'"
            ).fetchone()[0]
        self.assertEqual([(b["hour"], b["seconds"]) for b in buckets], [(11, 5), (12, 5)])
        self.assertEqual(total, 10)

    def test_local_midnight_splits_day_and_hour(self):
        from datetime import datetime
        first = datetime(2026, 10, 17, 23, 59, 55, tzinfo=tracking.ZONE).timestamp()
        with tracking.connect() as db:
            tracking.add_seconds(db, "TX", first, first + 10)
            days = db.execute(
                "SELECT day,seconds FROM study_day WHERE subject='TX' ORDER BY day"
            ).fetchall()
            hours = db.execute(
                "SELECT day,hour,seconds FROM study_hour WHERE subject='TX' ORDER BY day,hour"
            ).fetchall()
        self.assertEqual([(d["day"], d["seconds"]) for d in days],
                         [("2026-10-17", 5), ("2026-10-18", 5)])
        self.assertEqual([(h["hour"], h["seconds"]) for h in hours], [(23, 5), (0, 5)])

    def test_self_overview_returns_live_kuwait_bucket_data(self):
        from datetime import datetime
        now = datetime.now(tracking.ZONE)
        first = now.replace(hour=10, minute=0, second=0, microsecond=0).timestamp()
        with tracking.connect() as db:
            tracking.add_seconds(db, "AA", first, first + 300)
            tracking.add_seconds(db, "TX", first + 60, first + 180)
        response = self.client.get("/api/self-overview")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["timezone"], "Asia/Kuwait")
        self.assertEqual(len(data["hours"]), 24)
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual(data["today_totals"]["AA"], 300)
        self.assertEqual(data["today_totals"]["TX"], 120)
        self.assertEqual(data["hours"][10]["AA"], 300)
        self.assertEqual(data["hours"][10]["TX"], 120)

    def test_overview_rejects_future_date(self):
        from datetime import datetime, timedelta
        date_str = (datetime.now(tracking.ZONE).date() + timedelta(days=1)).isoformat()
        result = self.client.get("/api/self-overview?date=" + date_str)
        self.assertEqual(result.status_code, 400)

    def test_rejects_invalid_payload(self):
        response = self.client.post("/api/study-time/pulse", json={
            "tab_id": "invalid", "seq": 1, "active": True, "subject": "AA"
        })
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
