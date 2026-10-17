"""Private single-owner sign-in for Jay Study Hub.

Configure HUB_PASSWORD_HASH (preferred) or HUB_ACCESS_PASSWORD and
FLASK_SECRET_KEY in the Bot-Hosting environment, never in Git.
"""
import hmac
import os
from urllib.parse import urlsplit

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

auth = Blueprint("auth", __name__)


def configured():
    return bool(os.getenv("HUB_PASSWORD_HASH") or os.getenv("HUB_ACCESS_PASSWORD"))


def password_valid(submitted):
    if not isinstance(submitted, str):
        return False
    hashed = os.getenv("HUB_PASSWORD_HASH", "")
    if hashed:
        try:
            return check_password_hash(hashed, submitted)
        except (ValueError, TypeError):
            return False
    plain = os.getenv("HUB_ACCESS_PASSWORD", "")
    return bool(plain) and hmac.compare_digest(submitted, plain)


def safe_destination(value):
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    if urlsplit(value).netloc or value.startswith("/\\"):
        return "/"
    return value


@auth.before_app_request
def enforce_private_access():
    # No arbitrary public read/write access to study times, grades, or answers.
    if request.endpoint in ("auth.login", "health", "static"):
        return None
    if not configured():
        return render_template("setup_required.html"), 503
    if not session.get("hub_signed_in"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Sign in required"}), 401
        destination = request.full_path.rstrip("?") if request.method == "GET" else "/"
        return redirect(url_for("auth.login", next=safe_destination(destination)))


@auth.route("/login", methods=["GET", "POST"])
def login():
    next_url = safe_destination(request.values.get("next", "/"))
    if not configured():
        return render_template("setup_required.html"), 503
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password_valid(password):
            session.clear()
            session["hub_signed_in"] = True
            session.permanent = True
            return redirect(next_url)
        error = "Incorrect password."
    return render_template("login.html", error=error, next_url=next_url)


@auth.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
