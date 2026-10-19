"""Smoke tests for the isolated clean Jay Study Hub deployment."""
import importlib
import os
import tempfile
import unittest
from pathlib import Path


class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.saved = {}
        changes = {
            "AA_DB_PATH": str(Path(cls.tmp.name) / "aa_hub.db"),
            "TX_DB_PATH": str(Path(cls.tmp.name) / "tx_hub.db"),
            "STUDY_TIME_DB_PATH": str(Path(cls.tmp.name) / "study_time.db"),
            "BOARD_STORAGE_PATH": str(Path(cls.tmp.name) / "board_data"),
            "HUB_ACCESS_PASSWORD": "testing-only-password",
            "FLASK_SECRET_KEY": "testing-secret-should-be-random-in-production",
            "HUB_ALLOW_HTTP": "1",
        }
        for name, value in changes.items():
            cls.saved[name] = os.environ.get(name)
            os.environ[name] = value
        cls.application = importlib.import_module("app")
        cls.application.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)

    @classmethod
    def tearDownClass(cls):
        for name, value in cls.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.application.app.test_client()

    def login(self):
        response = self.client.post("/login", data={
            "password": "testing-only-password",
            "next": "/self-overview",
        })
        self.assertEqual(response.status_code, 302, response.data)
        return response

    def test_private_hub_requires_sign_in(self):
        for path in ("/", "/tx/", "/self-overview", "/chapters", "/attempts"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertTrue(response.headers["Location"].startswith("/login"), path)
        self.assertEqual(self.client.get("/api/self-overview").status_code, 401)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_private_portals_and_overview(self):
        self.login()
        for path in ("/", "/tx/", "/self-overview", "/chapters", "/tests", "/weaknesses", "/study-board?subject=AA&chapter=7", "/study-board?subject=TX&chapter=1A"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path + ": " + str(response.data[:200]))
        response = self.client.get("/api/self-overview")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["hours"]), 24)

    def test_logout_closes_session(self):
        self.login()
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.post("/logout").status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_aa_progress_is_not_overwritten_on_restart(self):
        db = self.application.get_db()
        db.execute(
            "UPDATE chapter_progress SET latest_mark=94, retested=1, applied=1, status='Complete' WHERE chapter=1"
        )
        db.commit()
        db.close()
        self.application.init_db()
        db = self.application.get_db()
        row = db.execute(
            "SELECT latest_mark,retested,applied,status FROM chapter_progress WHERE chapter=1"
        ).fetchone()
        db.close()
        self.assertEqual((row["latest_mark"], row["retested"], row["applied"], row["status"]),
                         (94, 1, 1, "Complete"))

    def test_bad_password_does_not_grant_access(self):
        response = self.client.post("/login", data={"password": "incorrect"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 302)


if __name__ == "__main__":
    unittest.main()
