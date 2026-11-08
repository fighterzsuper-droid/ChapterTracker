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



PUBLIC_DOMAIN = "s31tp7axkt.apps.bot-hosting.cloud"


def _verified_deployment_from_api(token):
    """Find the exact F7 deployment visible to the API key.

    Never select based solely on a display name: both the public domain and
    linked GitHub repository must match our known F7 website.
    Requires deployments:read in addition to deployments:write.
    Returns (deployment_id, diagnostic) for the admin UI.
    """
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "Jay-ACCA-FR-Portal",
    }
    req = Request("https://bot-hosting.net/api/v1/deployments", headers=headers)
    try:
        with urlopen(req, timeout=12) as res:
            data = json.load(res)
    except HTTPError as exc:
        if exc.code in (401, 403):
            return None, "The existing Bot-Hosting key cannot list deployments. Add deployments:read, and ensure the key belongs to the deployment owner or an authorised collaborator."
        return None, "Could not look up deployments through Bot-Hosting (HTTP " + str(exc.code) + ")."
    except (URLError, OSError, TimeoutError, ValueError):
        return None, "Could not verify which deployments this API key can access."
    deployments = data.get("deployments", []) if isinstance(data, dict) else []
    if not isinstance(deployments, list):
        return None, "The Bot-Hosting deployment list returned an unexpected format."
    candidates = []
    for row in deployments:
        if not isinstance(row, dict):
            continue
        did = str(row.get("id", "")).strip()
        if not did or not re.fullmatch(r"[A-Za-z0-9_-]{5,90}", did):
            continue
        domains = row.get("domains") or {}
        if not isinstance(domains, dict):
            continue
        url = str(domains.get("url") or "")
        subdomain = str(domains.get("subdomain") or "")
        if PUBLIC_DOMAIN not in (url, subdomain) and not url.startswith("https://" + PUBLIC_DOMAIN):
            continue
        # Verify the connected source before allowing a remotely triggered restart.
        req = Request("https://bot-hosting.net/api/v1/deployments/" + did + "/git", headers=headers)
        try:
            with urlopen(req, timeout=10) as response:
                git_data = json.load(response)
        except (HTTPError, URLError, ValueError, OSError, TimeoutError):
            continue
        if not isinstance(git_data, dict):
            continue
        if git_data.get("repo") == REPOSITORY and git_data.get("branch") == BRANCH:
            candidates.append(did)
    if len(candidates) == 1:
        return candidates[0], "Verified the F7 domain and GitHub link using the API."
    if not deployments:
        return None, "This API key sees no deployments. Create a key from the Bot-Hosting account that owns this F7 deployment, or obtain authorised access."
    return None, "The key can list deployments but cannot see the linked F7 website with the expected domain and GitHub repo. Check account permissions and deployment ownership."


def _call_deployment_sync(token, did):
    url = "https://bot-hosting.net/api/v1/deployments/" + did + "/sync"
    req = Request(
        url, data=b"{}",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Jay-ACCA-FR-Portal",
        }, method="POST",
    )
    with urlopen(req, timeout=65) as response:
        return json.load(response)


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
            if _LAST_PULL_AT and time.monotonic() - _LAST_PULL_AT < 45:
                return jsonify({"error": "A sync was requested recently. Allow the deployment to restart."}), 429
            _LAST_PULL_AT = time.monotonic()
            # A fixed target + empty JSON tells Bot-Hosting to retain its linked repo and branch.
            # The platform pulls from GitHub and restarts the deployment if it was running.
            try:
                data = _call_deployment_sync(token, deployment_id)
            except HTTPError as exc:
                if exc.code in (401, 403):
                    return jsonify({"error": "Bot-Hosting rejected the key or the key lacks deployments:write access to this deployment. Confirm the account and key permissions."}), 502
                if exc.code == 404:
                    resolved_id, why = _verified_deployment_from_api(token)
                    if resolved_id and resolved_id != deployment_id:
                        try:
                            data = _call_deployment_sync(token, resolved_id)
                        except HTTPError as retry_error:
                            return jsonify({"error": "Deployment identified as " + resolved_id + " but sync failed (HTTP " + str(retry_error.code) + "). Check the key's deployments:write permission."}), 502
                    else:
                        return jsonify({"error": "Bot-Hosting returned 404 for deployment " + deployment_id + ". " + why + " You can use Pull now from the Bot-Hosting GitHub panel without this API key."}), 502
                else:
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
