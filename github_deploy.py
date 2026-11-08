"""Admin-only GitHub deployment controls for the hosted ACCA FR portal.

The pull operation uses Bot-Hosting's official deployments.sync endpoint,
rather than modifying running code with shell commands. Never expose API keys
to the browser or permit user-controlled deployment IDs, repositories or refs.
"""
import hmac
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import abort, jsonify, request, session

REPOSITORY = "fighterzsuper-droid/ChapterTracker"
BRANCH = "main"
DEFAULT_DEPLOYMENT_ID = "e4fcc621-608a-48e3-abba-f939755001a2"
BASE_DIR = Path(__file__).resolve().parent
_SHA_RE = re.compile(r"^[a-fA-F0-9]{7,40}$")
_PULL_LOCK = threading.Lock()
_LAST_PULL_AT = 0.0


def _deployed_commit():
    """A git checkout is optional on Bot-Hosting; an absent SHA is not an error."""
    try:
        result = subprocess.run(
            ["git", "-C", str(BASE_DIR), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        value = result.stdout.strip()
        if result.returncode == 0 and _SHA_RE.fullmatch(value):
            return value
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _remote_commit():
    """Read the public main branch without transmitting the deployment key."""
    req = Request(
        "https://api.github.com/repos/" + REPOSITORY + "/commits/" + BRANCH,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Jay-ACCA-FR-Portal"},
    )
    try:
        with urlopen(req, timeout=7) as response:
            payload = json.load(response)
        value = str(payload.get("sha", ""))
        return value if _SHA_RE.fullmatch(value) else None
    except (HTTPError, URLError, ValueError, OSError, TimeoutError):
        return None


def register_github_deploy(app, current_user, is_admin):
    """Install safe GET status and POST sync endpoints on the Flask application."""
    def admin_only():
        user = current_user()
        if not user:
            abort(401)
        if not is_admin(user):
            abort(403)
        return user

    @app.get("/api/admin/github/status")
    def admin_github_status():
        admin_only()
        token_present = bool(os.getenv("BOT_HOSTING_API_KEY", "").strip())
        deployment_id = os.getenv("BOT_HOSTING_DEPLOYMENT_ID", DEFAULT_DEPLOYMENT_ID).strip()
        running = _deployed_commit()
        remote = _remote_commit()
        return jsonify({
            "repository": REPOSITORY,
            "branch": BRANCH,
            "configured": token_present and bool(deployment_id),
            "running_commit": running,
            "remote_commit": remote,
            "update_available": (running != remote) if running and remote else None,
            "panel_url": "https://bot-hosting.net/a/d/" + DEFAULT_DEPLOYMENT_ID + "/github",
            "setup_hint": (
                "Set BOT_HOSTING_API_KEY in Bot-Hosting private environment variables. "
                "Create the key under Account > Developer with deployments:write scope. "
                "Keep the key secret. BOT_HOSTING_DEPLOYMENT_ID is optional for the current deployment."
            ) if not token_present else None,
        })

    @app.post("/api/admin/github/pull")
    def admin_github_pull():
        global _LAST_PULL_AT
        admin_only()
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not supplied or not expected or not hmac.compare_digest(supplied, expected):
            return jsonify({"error": "Invalid session token. Refresh the page and try again."}), 403
        token = os.getenv("BOT_HOSTING_API_KEY", "").strip()
        deployment_id = os.getenv("BOT_HOSTING_DEPLOYMENT_ID", DEFAULT_DEPLOYMENT_ID).strip()
        if not token:
            return jsonify({"error": "Bot-Hosting API key is not configured. See Management setup instructions."}), 503
        if not deployment_id or not re.fullmatch(r"[A-Za-z0-9_-]{5,90}", deployment_id):
            return jsonify({"error": "The deployment ID is not configured correctly."}), 503
        if not _PULL_LOCK.acquire(blocking=False):
            return jsonify({"error": "A GitHub sync request is already in progress."}), 409
        try:
            if time.monotonic() - _LAST_PULL_AT < 45:
                return jsonify({"error": "A sync was requested recently. Allow the deployment to restart."}), 429
            _LAST_PULL_AT = time.monotonic()
            # A fixed target + empty JSON tells Bot-Hosting to retain its linked repo and branch.
            # The platform pulls from GitHub and restarts the deployment if it was running.
            url = "https://bot-hosting.net/api/v1/deployments/" + deployment_id + "/sync"
            req = Request(
                url, data=b"{}",
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Jay-ACCA-FR-Portal",
                },
                method="POST",
            )
            try:
                with urlopen(req, timeout=65) as response:
                    data = json.load(response)
            except HTTPError as exc:
                if exc.code in (401, 403):
                    return jsonify({"error": "Bot-Hosting rejected the API key or required deployments:write permission."}), 502
                if exc.code == 404:
                    return jsonify({"error": "Bot-Hosting deployment was not found. Check BOT_HOSTING_DEPLOYMENT_ID."}), 502
                return jsonify({"error": "Bot-Hosting could not sync the deployment (HTTP " + str(exc.code) + ")."}), 502
            except (URLError, OSError, TimeoutError, ValueError):
                # During a self-restart the connection can disappear before the API replies.
                return jsonify({"error": "The sync response could not be confirmed. Check the deployment in Bot-Hosting before retrying."}), 502
            if not isinstance(data, dict) or data.get("ok") is not True:
                return jsonify({"error": "Bot-Hosting did not confirm a successful sync. Check its GitHub panel."}), 502
            commit = data.get("commit")
            if not isinstance(commit, str) or not _SHA_RE.fullmatch(commit):
                commit = None
            return jsonify({
                "ok": True,
                "commit": commit,
                "message": "Bot-Hosting confirmed the GitHub pull. The deployment is restarting if it was running.",
            })
        finally:
            _PULL_LOCK.release()
