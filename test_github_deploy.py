"""CI checks for admin-only Bot-Hosting GitHub pull support (no live API calls)."""
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from flask import Flask
import github_deploy


class FakeResponse:
    def __init__(self, content):
        self.content = json.dumps(content).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        return False
    def read(self, *_):
        return self.content


class GitHubDeployTests(unittest.TestCase):
    def setUp(self):
        github_deploy._LAST_PULL_AT = 0
        self.user = None
        self.app = Flask(__name__)
        self.app.secret_key = "only-for-unit-tests"
        github_deploy.register_github_deploy(
            self.app,
            lambda: self.user,
            lambda user: bool(user and user.get("admin")),
        )
        self.client = self.app.test_client()

    def auth(self, admin):
        self.user = {"admin": bool(admin)}
        with self.client.session_transaction() as sess:
            sess["csrf_token"] = "test-csrf"

    def test_login_and_admin_required(self):
        self.assertEqual(self.client.get("/api/admin/github/status").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/github/pull").status_code, 401)
        self.auth(admin=False)
        self.assertEqual(self.client.get("/api/admin/github/status").status_code, 403)
        self.assertEqual(self.client.post("/api/admin/github/pull").status_code, 403)

    def test_status_shows_public_version_but_not_secret(self):
        self.auth(admin=True)
        with patch.dict(os.environ, {"BOT_HOSTING_API_KEY": ""}), \
             patch.object(github_deploy, "_remote_commit", return_value="a" * 40), \
             patch.object(github_deploy, "_deployed_commit", return_value="b" * 40):
            res = self.client.get("/api/admin/github/status")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json["configured"])
        self.assertTrue(res.json["update_available"])
        self.assertEqual(res.json["repository"], "fighterzsuper-droid/ChapterTracker")
        self.assertIn("BOT_HOSTING_API_KEY", res.json["setup_hint"])
        self.assertNotIn("Authorization", res.get_data(as_text=True))

    def test_pull_requires_csrf_and_server_secret(self):
        self.auth(admin=True)
        with patch.dict(os.environ, {"BOT_HOSTING_API_KEY": ""}):
            res = self.client.post("/api/admin/github/pull", headers={"X-CSRF-Token": "test-csrf"})
            self.assertEqual(res.status_code, 503)
        with patch.dict(os.environ, {"BOT_HOSTING_API_KEY": "bhk_fake_test"}):
            res = self.client.post("/api/admin/github/pull", headers={"X-CSRF-Token": "invalid"})
            self.assertEqual(res.status_code, 403)

    def test_pull_calls_only_fixed_bot_hosting_sync_endpoint(self):
        self.auth(admin=True)
        with patch.dict(os.environ, {"BOT_HOSTING_API_KEY": "bhk_fake_test"}), \
             patch.object(github_deploy, "urlopen", return_value=FakeResponse({"ok": True, "commit": "abcdef123456789"})) as urlopen_mock:
            result = self.client.post(
                "/api/admin/github/pull",
                headers={"X-CSRF-Token": "test-csrf", "Content-Type": "application/json"},
                json={"repo": "attacker/other-repository", "branch": "malicious"},
            )
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        self.assertEqual(result.json["commit"], "abcdef123456789")
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "https://bot-hosting.net/api/v1/deployments/e4fcc621-608a-48e3-abba-f939755001a2/sync")
        self.assertEqual(req.data, b"{}")
        self.assertEqual(req.get_header("Authorization"), "Bearer bhk_fake_test")

    def test_404_reports_account_or_deployment_id_issue_without_token(self):
        self.auth(admin=True)
        not_found = HTTPError("https://bot-hosting.net/api/v1/deployments/id/sync", 404, "Not found", None, None)
        with patch.dict(os.environ, {"BOT_HOSTING_API_KEY": "bhk_fake_test"}), \
             patch.object(github_deploy, "_call_deployment_sync", side_effect=not_found), \
             patch.object(github_deploy, "_verified_deployment_from_api",
                          return_value=(None, "This API key sees no deployments.")):
            result = self.client.post("/api/admin/github/pull", headers={"X-CSRF-Token": "test-csrf"})
        self.assertEqual(result.status_code, 502)
        self.assertIn("This API key sees no deployments", result.json["error"])
        self.assertNotIn("bhk_fake_test", result.get_data(as_text=True))

    def test_404_safe_recovery_requires_verified_f7_domain_and_repository(self):
        self.auth(admin=True)
        not_found = HTTPError("https://bot-hosting.net/api/v1/deployments/id/sync", 404, "Not found", None, None)
        recovered_id = "dep_verified_f7_id"
        with patch.dict(os.environ, {"BOT_HOSTING_API_KEY": "bhk_fake_test"}), \
             patch.object(github_deploy, "_call_deployment_sync",
                          side_effect=[not_found, {"ok": True, "commit": "abc123def"}]) as sync, \
             patch.object(github_deploy, "_verified_deployment_from_api",
                          return_value=(recovered_id, "Verified domain and GitHub.")):
            result = self.client.post("/api/admin/github/pull", headers={"X-CSRF-Token": "test-csrf"})
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        self.assertEqual(sync.call_args_list[1].args[1], recovered_id)

    def test_pull_rejects_second_request_within_cooldown(self):
        self.auth(admin=True)
        with patch.dict(os.environ, {"BOT_HOSTING_API_KEY": "bhk_fake_test"}), \
             patch.object(github_deploy, "urlopen", return_value=FakeResponse({"ok": True, "commit": "abc123def"})):
            first = self.client.post("/api/admin/github/pull", headers={"X-CSRF-Token": "test-csrf"})
            second = self.client.post("/api/admin/github/pull", headers={"X-CSRF-Token": "test-csrf"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)


if __name__ == "__main__":
    unittest.main()
