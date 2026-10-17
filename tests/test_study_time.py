"""Unit tests for the server's conservative study-time accounting.

Run from repository root: python -m unittest discover -s tests -v
"""
import tempfile
import time
import unittest
from pathlib import Path

from flask import Flask
import study_time as tracking


class StudyTimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = tracking.DB
        tracking.DB = Path(self.temp.name) / "study_time.db"
        tracking.initialize()
        self.app = Flask(__name__)
        self.app.register_blueprint(tracking.study_time)
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

    def test_rejects_invalid_payload(self):
        response = self.client.post("/api/study-time/pulse", json={
            "tab_id": "invalid", "seq": 1, "active": True, "subject": "AA"
        })
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
