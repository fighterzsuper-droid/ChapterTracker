import gzip
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, Response, abort, flash, jsonify, redirect, render_template_string, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("F7_DB_PATH", str(BASE_DIR / "f7_portal.db")))
FR_PORTAL_PARTS = [BASE_DIR / f"fr_portal_v7.gz.part{i}" for i in range(4)]
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
ADMIN_EMAIL = "jayakiran804@gmail.com"

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=3 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("HUB_ALLOW_HTTP") != "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def db_connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db_connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        password_hash TEXT,
        google_sub TEXT UNIQUE,
        avatar TEXT,
        google_picture TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub);
    CREATE TABLE IF NOT EXISTS progress_topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0 CHECK(progress IN (0,50,100)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_progress_topics_user ON progress_topics(user_id);
    """)
    conn.commit()
    conn.close()

def purge_legacy_f6_f8_data():
    """Owner-requested one-way F6/F8 cleanup for the F7-only deployment."""
    marker = DB_PATH.with_suffix(DB_PATH.suffix + ".legacy-purged")
    if marker.exists():
        return

    files = {
        BASE_DIR / "aa_hub.db",
        BASE_DIR / "tx_hub.db",
        BASE_DIR / "study_time.db",
        BASE_DIR / "study_time.sqlite3",
    }
    for env_name in ("AA_DB_PATH", "TX_DB_PATH", "STUDY_TIME_DB_PATH"):
        value = os.getenv(env_name)
        if value:
            files.add(Path(value))

    for path in files:
        try:
            if path.resolve() == DB_PATH.resolve():
                continue
            if path.is_file():
                path.unlink()
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(path) + suffix)
                if sidecar.is_file():
                    sidecar.unlink()
        except OSError:
            pass

    dirs = {BASE_DIR / "board_data"}
    if os.getenv("BOARD_STORAGE_PATH"):
        dirs.add(Path(os.environ["BOARD_STORAGE_PATH"]))
    for path in dirs:
        try:
            resolved = path.resolve()
            if resolved not in (Path("/").resolve(), BASE_DIR.resolve(), BASE_DIR.parent.resolve()) and path.is_dir():
                shutil.rmtree(path)
        except OSError:
            pass

    # A Bot-Hosting Git sync may leave old source files behind. They are
    # intentionally removed because this deployment is now FR/F7 only.
    for name in ("tx_hub.py", "board.py", "study_time.py", "watcher.py", "restart_ui.py", "security.py"):
        try:
            path = BASE_DIR / name
            if path.is_file():
                path.unlink()
        except OSError:
            pass
    for name in ("templates", "static"):
        try:
            path = BASE_DIR / name
            if path.is_dir():
                shutil.rmtree(path)
        except OSError:
            pass

    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(utc_now(), encoding="utf-8")
    except OSError:
        pass

def normalize_email(value):
    return (value or "").strip().lower()

def normalize_username(value):
    return (value or "").strip().lower()

def valid_email(value):
    value = normalize_email(value)
    return bool(value and "@" in value and "." in value.rsplit("@", 1)[-1])

def get_user_by_id(user_id):
    if not user_id:
        return None
    conn = db_connect()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return row

def current_user():
    return get_user_by_id(session.get("user_id"))

def login_user(row):
    session.clear()
    session["user_id"] = row["id"]
    session.permanent = True

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        session["csrf_token"] = token
    return token

def valid_csrf():
    submitted = request.form.get("csrf_token")
    expected = session.get("csrf_token")
    return bool(submitted and expected and hmac.compare_digest(submitted, expected))

CSS = """
*{box-sizing:border-box}html,body{height:100%;margin:0}body{font-family:Arial,Helvetica,sans-serif;background:linear-gradient(135deg,#0b2942,#145c88);color:#173851;overflow:hidden}
.shell{height:100%;display:grid;place-items:center;padding:22px}.card{width:min(980px,94vw);height:min(690px,92vh);background:#fff;border-radius:16px;box-shadow:0 28px 85px rgba(0,0,0,.32);display:grid;grid-template-columns:1.05fr .95fr;overflow:hidden}
.hero{padding:48px;background:linear-gradient(145deg,#0d3554,#17618e);color:#fff;display:flex;flex-direction:column;justify-content:space-between}.brand{font-size:30px;font-weight:900}.brand b{color:#ff3940;margin-right:8px}.hero h1{font-size:34px;line-height:1.08;margin:0 0 14px}.hero p{color:#d6e9f5;line-height:1.55;max-width:450px}.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{border:1px solid rgba(255,255,255,.28);background:rgba(255,255,255,.08);padding:7px 10px;border-radius:999px;font-size:12px}
.form{padding:38px 44px;display:flex;flex-direction:column;justify-content:center;overflow:auto}.form h2{font-size:27px;margin:0 0 5px;color:#123652}.sub{color:#718397;margin:0 0 17px}.tabs{display:grid;grid-template-columns:1fr 1fr;gap:5px;background:#eef4f8;padding:4px;border-radius:8px;margin-bottom:14px}.tab{height:35px;border:0;background:transparent;border-radius:6px;font-weight:800;color:#557087;cursor:pointer}.tab.active{background:#fff;color:#123652;box-shadow:0 1px 5px rgba(20,50,70,.12)}
.field{margin-bottom:10px}.field label{display:block;font-size:12px;font-weight:800;color:#36546b;margin-bottom:6px}.field input{width:100%;height:40px;border:1px solid #c7d4de;border-radius:6px;padding:8px 10px;outline:none}.field input:focus{border-color:#1b7abc;box-shadow:0 0 0 3px rgba(27,122,188,.12)}
.primary,.google{width:100%;height:43px;border-radius:6px;font-weight:800;cursor:pointer}.primary{border:1px solid #08629f;background:#0c70b7;color:#fff}.google{border:1px solid #bdcbd6;background:#fff;color:#263f54}.google:hover{background:#f7fafc}.g{display:inline-grid;place-items:center;width:22px;height:22px;border:1px solid #d5dce1;border-radius:50%;color:#4285f4;margin-right:7px;font-weight:900}
.divider{display:flex;align-items:center;gap:10px;color:#8a9aa7;font-size:11px;margin:11px 0}.divider:before,.divider:after{content:"";height:1px;background:#dfe6eb;flex:1}.notice{background:#eef6fb;border:1px solid #cfe1ed;border-radius:7px;padding:10px;font-size:12px;color:#547087;line-height:1.45;margin-top:12px}.flash{padding:9px;border-radius:6px;margin-bottom:10px;font-size:12px;font-weight:700}.flash.error{background:#fff0ef;border:1px solid #efc7c3;color:#a6251f}
.setup{max-width:680px;width:92vw;background:#fff;border-radius:14px;padding:32px;box-shadow:0 24px 70px rgba(0,0,0,.3)}.setup h1{margin-top:0;color:#123652}.setup pre{white-space:pre-wrap;background:#0f2638;color:#d9efff;padding:14px;border-radius:8px}.setup a{color:#0c70b7}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.full{grid-column:1/-1}
@media(max-width:760px){body{overflow:auto}.shell{height:auto;min-height:100%}.card{height:auto;grid-template-columns:1fr}.hero{padding:28px;min-height:250px}.form{padding:28px}.grid{grid-template-columns:1fr}.full{grid-column:auto}}
"""

LOGIN_PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ACCA FR Practice Portal</title><style>{{css}}</style></head><body><div class="shell"><div class="card"><section class="hero"><div class="brand"><b>ACCA</b> FR Portal</div><div><h1>Financial Reporting<br>practice & mocks</h1><p>F7-only practice portal for exam-standard mocks, analytics, retests and Section C teacher review.</p></div><div class="chips"><span class="chip">FR / F7</span><span class="chip">Sep 2026 - Jun 2027</span><span class="chip">Google + fallback login</span></div></section><section class="form"><h2>Sign in</h2><p class="sub">Continue to your Financial Reporting dashboard.</p>{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash {{category}}">{{message}}</div>{% endfor %}{% endwith %}<div class="tabs"><button id="lt" class="tab active" onclick="mode('login')">Sign in</button><button id="ct" class="tab" onclick="mode('create')">Create account</button></div><div id="login"><form method="post"><input type="hidden" name="csrf_token" value="{{csrf}}"><div class="field"><label>Username or email</label><input name="identifier" required></div><div class="field"><label>Password</label><input type="password" name="password" required></div><button class="primary">Sign in</button></form></div><div id="create" style="display:none"><form method="post" action="/register"><input type="hidden" name="csrf_token" value="{{csrf}}"><div class="field"><label>Display name</label><input name="display_name" value="Jayakiran" required></div><div class="field"><label>Username</label><input name="username" required></div><div class="field"><label>Email</label><input type="email" name="email" required></div><div class="field"><label>Fallback password</label><input type="password" name="password" minlength="8" required></div><button class="primary">Create account</button></form></div><div class="divider">OR</div><a href="/auth/google"><button class="google" type="button"><span class="g">G</span>Continue with Google</button></a><div class="notice">If a Google email is new, the portal asks once for a username and fallback password so you can still sign in if Google access is unavailable.</div></section></div></div><script>function mode(m){login.style.display=m==='login'?'block':'none';create.style.display=m==='create'?'block':'none';lt.classList.toggle('active',m==='login');ct.classList.toggle('active',m==='create')}</script></body></html>"""

COMPLETE_PAGE = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Finish account setup</title><style>{{css}}</style></head><body><div class="shell"><div class="setup"><h1>Finish your Google account setup</h1><p>Google verified <b>{{pending.email}}</b>. Choose a username and fallback password.</p>{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash {{category}}">{{message}}</div>{% endfor %}{% endwith %}<form method="post"><input type="hidden" name="csrf_token" value="{{csrf}}"><div class="grid"><div class="field full"><label>Display name</label><input name="display_name" value="{{pending.name}}" required></div><div class="field"><label>Username</label><input name="username" required></div><div class="field"><label>Fallback password</label><input type="password" name="password" minlength="8" required></div></div><button class="primary">Create my FR account</button></form><p><a href="/login">Cancel</a></p></div></div></body></html>"""

GOOGLE_SETUP_PAGE = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Google OAuth setup</title><style>{{css}}</style></head><body><div class="shell"><div class="setup"><h1>Google sign-in needs Bot-Hosting secrets</h1><p>The real OAuth flow is already installed. Set these private variables on Bot-Hosting:</p><pre>GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
FLASK_SECRET_KEY=long-random-secret
F7_DB_PATH=/persistent/path/f7_portal.db</pre><p>Add this exact Google authorised redirect URI:</p><pre>{{redirect_uri}}</pre><p>Then restart the deployment. Never commit the client secret to GitHub.</p><p><a href="/login">Return to sign in</a></p></div></div></body></html>"""

def render_login():
    return render_template_string(LOGIN_PAGE, css=CSS, csrf=csrf_token())

def google_redirect_uri():
    configured = (os.getenv("GOOGLE_REDIRECT_URI") or "").strip()
    if configured:
        return configured
    scheme = "http" if os.getenv("HUB_ALLOW_HTTP") == "1" else "https"
    return url_for("google_callback", _external=True, _scheme=scheme)

def google_configured():
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))

def google_exchange(code):
    data = urlencode({
        "code": code,
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "redirect_uri": google_redirect_uri(),
        "grant_type": "authorization_code",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data, headers={"Content-Type":"application/x-www-form-urlencoded"}, method="POST")
    with urlopen(req, timeout=15) as response:
        token = json.load(response)
    access_token = token.get("access_token")
    if not access_token:
        raise ValueError("No access token")
    req = Request("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization":"Bearer " + access_token})
    with urlopen(req, timeout=15) as response:
        return json.load(response)

def is_admin(row):
    return bool(row and normalize_email(row["email"]) == ADMIN_EMAIL)

def user_public(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "displayName": row["display_name"],
        "avatar": row["avatar"] or row["google_picture"] or "",
        "googleLinked": bool(row["google_sub"]),
        "role": "admin" if is_admin(row) else "student",
    }

@app.route("/login", methods=["GET","POST"])
def login():
    if current_user() and request.method == "GET":
        return redirect(url_for("portal"))
    if request.method == "POST":
        if not valid_csrf():
            abort(400)
        identifier = (request.form.get("identifier") or "").strip().lower()
        password = request.form.get("password") or ""
        conn = db_connect()
        row = conn.execute("SELECT * FROM users WHERE lower(username)=? OR lower(email)=?", (identifier,identifier)).fetchone()
        conn.close()
        if row and row["password_hash"] and check_password_hash(row["password_hash"], password):
            login_user(row)
            return redirect(url_for("portal"))
        flash("Incorrect username/email or password.", "error")
    return render_login()

@app.post("/register")
def register():
    if not valid_csrf():
        abort(400)
    display_name = (request.form.get("display_name") or "").strip()
    username = normalize_username(request.form.get("username"))
    email = normalize_email(request.form.get("email"))
    password = request.form.get("password") or ""
    if not display_name or not USERNAME_RE.fullmatch(username) or not valid_email(email) or len(password) < 8:
        flash("Use a 3-32 character username and a password of at least 8 characters.", "error")
        return redirect(url_for("login"))
    conn = db_connect()
    try:
        cur = conn.execute("""INSERT INTO users (username,email,display_name,password_hash,google_sub,avatar,google_picture,created_at,updated_at)
                              VALUES (?,?,?,?,NULL,'','',?,?)""",
                           (username,email,display_name,generate_password_hash(password),utc_now(),utc_now()))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        conn.close()
        flash("That username or email is already registered.", "error")
        return redirect(url_for("login"))
    conn.close()
    login_user(row)
    return redirect(url_for("portal"))

@app.route("/auth/google")
def google_start():
    if not google_configured():
        return render_template_string(GOOGLE_SETUP_PAGE, css=CSS, redirect_uri=google_redirect_uri())
    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))

@app.route("/auth/google/callback")
def google_callback():
    if not google_configured():
        return redirect(url_for("google_start"))
    state = request.args.get("state") or ""
    expected = session.pop("google_oauth_state", "")
    if not expected or not hmac.compare_digest(state, expected):
        abort(400)
    code = request.args.get("code")
    if not code:
        flash("Google sign-in was cancelled.", "error")
        return redirect(url_for("login"))
    try:
        info = google_exchange(code)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        flash("Google sign-in could not be completed. Check OAuth configuration.", "error")
        return redirect(url_for("login"))
    if not info.get("email_verified"):
        flash("Google did not return a verified email.", "error")
        return redirect(url_for("login"))

    email = normalize_email(info.get("email"))
    sub = str(info.get("sub") or "")
    if not email or not sub:
        flash("Google did not return the required account information.", "error")
        return redirect(url_for("login"))

    conn = db_connect()
    row = conn.execute("SELECT * FROM users WHERE google_sub=?", (sub,)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM users WHERE lower(email)=?", (email,)).fetchone()
        if row:
            if row["google_sub"] and row["google_sub"] != sub:
                conn.close()
                flash("That email is already linked to another Google account.", "error")
                return redirect(url_for("login"))
            conn.execute("UPDATE users SET google_sub=?,google_picture=?,updated_at=? WHERE id=?",
                         (sub,info.get("picture") or "",utc_now(),row["id"]))
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
    conn.close()

    if row:
        login_user(row)
        return redirect(url_for("portal"))

    session["pending_google"] = {
        "sub": sub,
        "email": email,
        "name": (info.get("name") or email.split("@",1)[0]).strip(),
        "picture": info.get("picture") or "",
    }
    return redirect(url_for("complete_google_account"))

@app.route("/complete-account", methods=["GET","POST"])
def complete_google_account():
    pending = session.get("pending_google")
    if not pending:
        return redirect(url_for("login"))
    if request.method == "POST":
        if not valid_csrf():
            abort(400)
        display_name = (request.form.get("display_name") or pending.get("name") or "").strip()
        username = normalize_username(request.form.get("username"))
        password = request.form.get("password") or ""
        if not display_name or not USERNAME_RE.fullmatch(username) or len(password) < 8:
            flash("Choose a 3-32 character username and an 8+ character fallback password.", "error")
        else:
            conn = db_connect()
            try:
                cur = conn.execute("""INSERT INTO users (username,email,display_name,password_hash,google_sub,avatar,google_picture,created_at,updated_at)
                                      VALUES (?,?,?,?,?,'',?,?,?)""",
                                   (username,pending["email"],display_name,generate_password_hash(password),pending["sub"],
                                    pending.get("picture") or "",utc_now(),utc_now()))
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
            except sqlite3.IntegrityError:
                conn.close()
                flash("That username is already taken.", "error")
            else:
                conn.close()
                session.pop("pending_google", None)
                login_user(row)
                return redirect(url_for("portal"))
    return render_template_string(COMPLETE_PAGE, css=CSS, pending=pending, csrf=csrf_token())

@app.route("/logout", methods=["GET","POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/profile", methods=["GET","PUT"])
@login_required
def api_profile():
    user = current_user()
    if request.method == "GET":
        return jsonify(user_public(user))
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    display_name = (data.get("displayName") or user["display_name"]).strip()
    username = normalize_username(data.get("username") or user["username"])
    email = normalize_email(data.get("email") or user["email"])
    password = data.get("password") or ""
    avatar = data.get("avatar", user["avatar"])
    if not display_name or not USERNAME_RE.fullmatch(username) or not valid_email(email):
        return jsonify({"error":"Invalid name, username or email."}), 400
    if password and len(password) < 8:
        return jsonify({"error":"New password must be at least 8 characters."}), 400
    if avatar and not (str(avatar).startswith("data:image/") or str(avatar).startswith("https://")):
        return jsonify({"error":"Unsupported profile picture."}), 400
    if len(str(avatar or "")) > 2700000:
        return jsonify({"error":"Profile picture is too large."}), 400

    conn = db_connect()
    try:
        password_hash = generate_password_hash(password) if password else user["password_hash"]
        conn.execute("""UPDATE users SET username=?,email=?,display_name=?,password_hash=?,avatar=?,updated_at=? WHERE id=?""",
                     (username,email,display_name,password_hash,avatar or "",utc_now(),user["id"]))
        conn.commit()
        updated = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error":"That username or email is already in use."}), 409
    conn.close()
    return jsonify(user_public(updated))

@app.route("/api/topics", methods=["GET","POST"])
@login_required
def api_topics():
    user = current_user()
    conn = db_connect()
    if request.method == "GET":
        rows = conn.execute(
            "SELECT id,title,progress,created_at,updated_at FROM progress_topics WHERE user_id=? ORDER BY id",
            (user["id"],)
        ).fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])

    if not is_admin(user):
        conn.close()
        return jsonify({"error":"Administrator access required."}), 403
    if not request.is_json:
        conn.close()
        abort(400)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    try:
        progress = int(data.get("progress", 0))
    except (TypeError, ValueError):
        progress = -1
    if not title or len(title) > 140 or progress not in (0,50,100):
        conn.close()
        return jsonify({"error":"Enter a topic name and use progress 0, 50 or 100."}), 400
    now = utc_now()
    cur = conn.execute(
        "INSERT INTO progress_topics (user_id,title,progress,created_at,updated_at) VALUES (?,?,?,?,?)",
        (user["id"], title, progress, now, now)
    )
    conn.commit()
    row = conn.execute(
        "SELECT id,title,progress,created_at,updated_at FROM progress_topics WHERE id=? AND user_id=?",
        (cur.lastrowid,user["id"])
    ).fetchone()
    conn.close()
    return jsonify(dict(row)), 201

@app.route("/api/topics/<int:topic_id>", methods=["PUT","DELETE"])
@login_required
def api_topic_item(topic_id):
    user = current_user()
    if not is_admin(user):
        return jsonify({"error":"Administrator access required."}), 403
    conn = db_connect()
    existing = conn.execute(
        "SELECT id,title,progress FROM progress_topics WHERE id=? AND user_id=?",
        (topic_id,user["id"])
    ).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error":"Topic not found."}), 404
    if request.method == "DELETE":
        conn.execute("DELETE FROM progress_topics WHERE id=? AND user_id=?", (topic_id,user["id"]))
        conn.commit()
        conn.close()
        return jsonify({"ok":True})
    if not request.is_json:
        conn.close()
        abort(400)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", existing["title"])).strip()
    try:
        progress = int(data.get("progress", existing["progress"]))
    except (TypeError, ValueError):
        progress = -1
    if not title or len(title) > 140 or progress not in (0,50,100):
        conn.close()
        return jsonify({"error":"Invalid topic or progress value."}), 400
    conn.execute(
        "UPDATE progress_topics SET title=?,progress=?,updated_at=? WHERE id=? AND user_id=?",
        (title,progress,utc_now(),topic_id,user["id"])
    )
    conn.commit()
    row = conn.execute(
        "SELECT id,title,progress,created_at,updated_at FROM progress_topics WHERE id=? AND user_id=?",
        (topic_id,user["id"])
    ).fetchone()
    conn.close()
    return jsonify(dict(row))

def portal_html_for(user):
    try:
        raw = b"".join(path.read_bytes() for path in FR_PORTAL_PARTS)
        html = gzip.decompress(raw).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError):
        abort(503)

    profile = json.dumps(user_public(user), ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("</head>", """<style>
#loginView{display:none!important}
[data-pview="profile"]{display:none!important}
.portalContent{position:relative}
.portalView{transform-origin:50% 0}
.portalView.portal-enter{animation:accaPanelIn .24s cubic-bezier(.2,.75,.25,1) both}
@keyframes accaPanelIn{from{opacity:0;transform:translateY(8px) scale(.995)}to{opacity:1;transform:translateY(0) scale(1)}}
.portalNavBtn{position:relative;overflow:hidden;transition:background .18s ease,color .18s ease,transform .18s ease}
.portalNavBtn:hover{transform:translateX(2px)}
.portalNavBtn.active:before{content:"";position:absolute;left:0;top:8px;bottom:8px;width:3px;border-radius:3px;background:#56b7ff}
.metricCard,.dashPanel,.compactMockCard,.managementPage,.profilePage{transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
.metricCard:hover,.compactMockCard:hover{transform:translateY(-2px);box-shadow:0 10px 26px rgba(26,70,103,.08);border-color:#bfd4e4}
.profilePopover{position:absolute;z-index:2500;right:26px;top:59px;width:330px;background:#fff;border:1px solid #cfdce6;border-radius:14px;box-shadow:0 20px 55px rgba(12,42,64,.2);padding:14px;opacity:0;transform:translateY(-8px) scale(.98);pointer-events:none;transition:opacity .16s ease,transform .16s ease}
.profilePopover.open{opacity:1;transform:translateY(0) scale(1);pointer-events:auto}
.profilePopHead{display:grid;grid-template-columns:48px 1fr;gap:11px;align-items:center;padding:5px 4px 13px;border-bottom:1px solid #e6edf2}
.profileAvatar.pop{width:48px;height:48px;font-size:16px}
.profilePopName{font-weight:900;color:#123653;font-size:15px}
.profilePopMail{font-size:11px;color:#718496;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.profilePopStatus{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}
.profilePopChip{font-size:9px;padding:3px 6px;border-radius:999px;background:#edf6fb;color:#2e688e;border:1px solid #d2e5f0}
.profilePopMenu{display:grid;gap:4px;padding-top:10px}
.profilePopItem{border:0;background:transparent;text-align:left;border-radius:8px;padding:10px 11px;font-weight:800;color:#24465f;cursor:pointer;display:flex;align-items:center;justify-content:space-between}
.profilePopItem:hover{background:#f1f7fb}
.profilePopItem.danger{color:#a12a22}
.dashboardV8{height:100%;display:grid;grid-template-rows:112px 96px 1fr;gap:13px;overflow:hidden}
.progressHero{background:linear-gradient(115deg,#0d3554 0%,#0c659f 58%,#1585bf 100%);border-radius:13px;padding:17px 20px;color:#fff;display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center;box-shadow:0 10px 28px rgba(13,60,92,.16);position:relative;overflow:hidden}
.progressHero:after{content:"";position:absolute;width:210px;height:210px;border:34px solid rgba(255,255,255,.06);border-radius:50%;right:-70px;top:-100px}
.progressEyebrow{font-size:10px;font-weight:900;letter-spacing:1.2px;color:#bfe6ff}
.progressTitle{font-size:20px;font-weight:900;margin:3px 0 7px}
.progressTrackBig{height:12px;background:rgba(255,255,255,.18);border-radius:999px;overflow:hidden;max-width:720px}
.progressFillBig{height:100%;background:linear-gradient(90deg,#8ce0ff,#fff);border-radius:999px;transition:width .5s cubic-bezier(.2,.8,.2,1)}
.progressMeta{display:flex;gap:13px;margin-top:8px;font-size:10px;color:#d7effc;flex-wrap:wrap}
.progressPercent{font-size:36px;font-weight:900;min-width:92px;text-align:right;position:relative;z-index:2}
.progressHeroActions{display:flex;flex-direction:column;align-items:flex-end;gap:8px;position:relative;z-index:2}
.progressManageBtn{height:34px;border:1px solid rgba(255,255,255,.45);background:rgba(255,255,255,.14);color:#fff;border-radius:8px;padding:0 12px;font-weight:900;font-size:11px;cursor:pointer;backdrop-filter:blur(4px);transition:background .16s ease,transform .16s ease}
.progressManageBtn:hover{background:rgba(255,255,255,.22);transform:translateY(-1px)}
.progressMiniTopics{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px;max-height:24px;overflow:hidden}
.progressTopicChip{font-size:9px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.16);padding:3px 6px;border-radius:999px}
.metricGridV8{display:grid;grid-template-columns:repeat(4,1fr);gap:11px}
.metricGridV8 .metricCard{padding:13px 15px}
.metricGridV8 .metricValue{font-size:24px;margin-top:4px}
.managementTabs{display:flex;gap:5px;padding:8px;background:#eef4f8;border-radius:9px}
.managementTab{height:34px;border:0;background:transparent;border-radius:7px;padding:0 13px;font-weight:900;color:#577084;cursor:pointer}
.managementTab.active{background:#fff;color:#123653;box-shadow:0 2px 8px rgba(25,54,75,.1)}
.topicMgmtWrap{height:calc(100% - 52px);display:grid;grid-template-columns:330px 1fr;min-height:0}
.topicAddPanel{padding:18px;border-right:1px solid #e0e8ee;background:#fbfcfd}
.topicAddCard{border:1px solid #d9e5ed;background:#fff;border-radius:11px;padding:16px;box-shadow:0 5px 18px rgba(31,65,90,.04)}
.topicAddCard h3{margin:0 0 5px;color:#143a58;font-size:16px}
.topicAddCard p{margin:0 0 13px;color:#718496;font-size:11px;line-height:1.45}
.topicAddRow{display:grid;gap:9px}
.topicAddRow input{height:39px;border:1px solid #c8d5de;border-radius:7px;padding:8px 10px}
.topicListPanel{padding:15px;overflow:auto}
.topicRow{display:grid;grid-template-columns:1fr auto auto auto;gap:10px;align-items:center;border:1px solid #dbe5ec;background:#fff;border-radius:10px;padding:11px 12px;margin-bottom:8px}
.topicName{font-weight:800;color:#173d5a;font-size:13px}
.topicStatus{font-size:10px;color:#708496;margin-top:2px}
.topicCheck{display:flex;align-items:center;gap:5px;font-size:11px;font-weight:800;color:#4e697c;background:#f5f8fa;border:1px solid #dbe4ea;border-radius:7px;padding:7px 8px;cursor:pointer}
.topicCheck input{accent-color:#0b70b7}
.topicDelete{border:0;background:#fff0ef;color:#a12a22;border-radius:7px;padding:7px 9px;font-weight:800;cursor:pointer}
.accessDenied{display:grid;place-items:center;height:100%;text-align:center;color:#5f7384}
@media(max-height:760px){.dashboardV8{grid-template-rows:96px 86px 1fr}.progressHero{padding:12px 17px}.progressTitle{font-size:17px}.progressPercent{font-size:30px}.metricGridV8 .metricCard{padding:9px 12px}}
</style></head>""")
    patch = r"""
<script>
window.__HOSTED_F7_USER__=__PROFILE__;
function __applyHostedProfile(p){
  try{
    if(typeof portalMeta==='undefined')return;
    var prev=(portalMeta.users||{})[p.username]||{};
    portalMeta.users={};
    portalMeta.users[p.username]=Object.assign({},prev,{username:p.username,displayName:p.displayName,email:p.email,avatar:p.avatar||'',googleLinked:!!p.googleLinked,role:p.role||'student',passwordHash:''});
    portalMeta.currentUser=p.username;
    if(typeof savePortalMeta==='function')savePortalMeta();
    portalSession={username:p.username,name:p.displayName};
    if(typeof state!=='undefined'){state.name=p.displayName;if(typeof save==='function')save();}
    if(typeof updateProfileChrome==='function')updateProfileChrome();
  }catch(e){console.error('Profile sync failed',e)}
}
async function __saveHostedProfile(extra){
  extra=extra||{};
  var p=window.__HOSTED_F7_USER__;
  var payload={
    displayName:(document.getElementById('pfName')&&document.getElementById('pfName').value.trim())||p.displayName,
    username:(document.getElementById('pfUser')&&document.getElementById('pfUser').value.trim())||p.username,
    email:(document.getElementById('pfEmail')&&document.getElementById('pfEmail').value.trim())||p.email,
    password:(document.getElementById('pfPass')&&document.getElementById('pfPass').value)||''
  };
  Object.assign(payload,extra);
  var res=await fetch('/api/profile',{method:'PUT',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(payload)});
  var body=await res.json().catch(function(){return {error:'Profile update failed.'}});
  if(!res.ok)throw new Error(body.error||'Profile update failed.');
  window.__HOSTED_F7_USER__=body;__applyHostedProfile(body);__installProfilePopover();var mg=document.querySelector('[data-pview="management"]');if(mg)mg.style.display=__isHostedAdmin()?'':'none';return body;
}

var __hostedTopics=[];
var __managementTab='topics';
function __isHostedAdmin(){return !!(window.__HOSTED_F7_USER__&&window.__HOSTED_F7_USER__.role==='admin')}
function __esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function __topicSummary(){
  var total=__hostedTopics.length,sum=0,done=0,half=0;
  __hostedTopics.forEach(function(t){var p=Number(t.progress)||0;sum+=p;if(p===100)done++;else if(p===50)half++});
  return {total:total,done:done,half:half,notStarted:Math.max(0,total-done-half),percent:total?Math.round(sum/total):0};
}
async function __loadTopics(renderAfter){
  try{
    var res=await fetch('/api/topics',{credentials:'same-origin'});
    if(res.ok)__hostedTopics=await res.json();
  }catch(e){console.error('Topic load failed',e)}
  if(renderAfter&&typeof renderPortalContent==='function')renderPortalContent();
}
async function addProgressTopic(){
  if(!__isHostedAdmin())return;
  var input=document.getElementById('newTopicName');if(!input)return;
  var title=input.value.trim();if(!title){if(typeof toast==='function')toast('Enter a topic name.');return}
  var res=await fetch('/api/topics',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({title:title,progress:0})});
  var body=await res.json().catch(function(){return {}});
  if(!res.ok){if(typeof toast==='function')toast(body.error||'Could not add topic.');return}
  input.value='';await __loadTopics(true);if(typeof toast==='function')toast('Topic added.');
}
async function setTopicProgress(id,progress){
  if(!__isHostedAdmin())return;
  var res=await fetch('/api/topics/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({progress:Number(progress)})});
  var body=await res.json().catch(function(){return {}});
  if(!res.ok){if(typeof toast==='function')toast(body.error||'Could not update topic.');return}
  await __loadTopics(true);
}
async function deleteProgressTopic(id){
  if(!__isHostedAdmin())return;
  if(!confirm('Delete this topic from your FR progress tracker?'))return;
  var res=await fetch('/api/topics/'+id,{method:'DELETE',credentials:'same-origin'});
  if(!res.ok){if(typeof toast==='function')toast('Could not delete topic.');return}
  await __loadTopics(true);
}
function __progressHero(){
  var s=__topicSummary();
  var chips=__hostedTopics.slice(0,6).map(function(t){return '<span class="progressTopicChip">'+__esc(t.title)+' · '+Number(t.progress)+'%</span>'}).join('');
  return '<div class="progressHero"><div><div class="progressEyebrow">FR / F7 SYLLABUS PROGRESS</div><div class="progressTitle">'+(s.total?s.done+' of '+s.total+' topics completed':'Build your topic tracker')+'</div><div class="progressTrackBig"><div class="progressFillBig" style="width:'+s.percent+'%"></div></div><div class="progressMeta"><span>'+s.done+' completed</span><span>'+s.half+' at 50%</span><span>'+s.notStarted+' not started</span></div><div class="progressMiniTopics">'+(chips||'<span class="progressTopicChip">No topics added yet</span>')+'</div></div><div class="progressHeroActions"><div class="progressPercent">'+s.percent+'%</div>'+(__isHostedAdmin()?'<button class="progressManageBtn" onclick="__managementTab=\'topics\';showPortalView(\'management\')">+ Add / Manage Topics</button>':'')+'</div></div>';
}
function portalOverviewV8(){
  var s=portalStats(),unfinished=!!(state.started&&!state.submitted&&(state.view!=='results'||state.retest&&state.retest.active));
  var recent=[].concat(state.history||[]).sort(function(a,b){return String(b.date||'').localeCompare(String(a.date||''))}).slice(0,5);
  var mocks=loadedMocks().filter(function(m){return m.available}).slice(0,3);
  var retested=(state.history||[]).filter(function(h){return h.retestResult&&h.retestResult.correct===h.retestResult.total}).length;
  return '<div class="portalView dashboardV8">'+__progressHero()+
  '<div class="metricGridV8"><div class="metricCard"><div class="metricLabel">Completed mocks</div><div class="metricValue">'+s.attempts+'</div><div class="metricHint">Exam-standard attempts</div></div>'+
  '<div class="metricCard"><div class="metricLabel">Average objective</div><div class="metricValue">'+s.avg+'/60</div><div class="metricHint">Across completed mocks</div></div>'+
  '<div class="metricCard"><div class="metricLabel">Best objective</div><div class="metricValue">'+s.best+'/60</div><div class="metricHint">Section C excluded</div></div>'+
  '<div class="metricCard"><div class="metricLabel">Retests cleared</div><div class="metricValue">'+retested+'</div><div class="metricHint">Weaknesses successfully retested</div></div></div>'+
  '<div class="dashLower"><div class="dashPanel"><div class="dashPanelHead"><span>Mock exams</span><button class="portalBtn" onclick="showPortalView(\'mocks\')">All mocks</button></div><div class="dashPanelBody">'+
  (mocks.map(function(m){var hist=(state.history||[]).filter(function(h){return (h.mockId||'mock1')===m.id}).sort(function(a,b){return String(b.date).localeCompare(String(a.date))});var last=hist[0],active=unfinished&&state.activeMockId===m.id;return '<div class="quickMock"><div><h3>'+__esc(m.title)+'</h3><p>'+(m.durationMinutes||180)+' min · '+(last?'Latest '+last.score+'/60':'No completed attempt yet')+'</p></div><button class="portalBtn primary" onclick="'+(active?'resumeExam()':"launchMock('"+m.id+"')")+'">'+(active?'Resume':'Start')+'</button></div>'}).join('')||'<div class="emptyState">No mocks available.</div>')+
  '</div></div><div class="dashPanel"><div class="dashPanelHead"><span>Recent attempts</span><button class="portalBtn" onclick="showPortalView(\'history\')">History</button></div><div class="dashPanelBody">'+
  (recent.length?'<table class="miniHistory"><thead><tr><th>Date</th><th>Mock</th><th>Objective</th></tr></thead><tbody>'+recent.map(function(h){return '<tr><td>'+__esc(formatDateShort(h.date))+'</td><td>'+__esc(mockName(h.mockId||'mock1'))+'</td><td class="miniScore">'+(h.score==null?0:h.score)+'/60</td></tr>'}).join('')+'</tbody></table>':'<div class="emptyState">No completed tests yet.</div>')+
  '</div></div></div></div>';
}
function __mockManagementHtml(){
  var mocks=loadedMocks();
  return '<div class="managementBody"><div class="importPanel"><div class="importDrop"><h3>Import mock file</h3><p>Upload a structured FR/F7 JSON mock. It becomes available in Mock Exams immediately.</p><input id="mockFileInput" class="filePicker" type="file" accept=".json,application/json"><button class="portalBtn primary" onclick="importMockFile()">Import selected file</button> <button class="portalBtn" onclick="downloadMockTemplate()">Download template</button><div id="importStatus" class="importStatus"></div></div><div class="schemaBox">30 objective questions + Q31/Q32 Section C.</div></div><div class="mockAdminList">'+mocks.map(function(m){return '<div class="adminMockRow"><div><h4>'+__esc(m.title)+' · '+(m.available?'Available':'Not loaded')+'</h4><p>'+__esc(m.id)+' · '+(m.durationMinutes||180)+' min · '+(m.data?'Imported':'Built-in/placeholder')+'</p></div><div class="adminActions"><button class="actionMini" onclick="editMockMeta(\''+m.id+'\')">Edit</button>'+(m.id!=='mock1'?'<button class="actionMini" onclick="toggleMockAvailable(\''+m.id+'\')">'+(m.available?'Disable':'Enable')+'</button><button class="actionMini" onclick="deleteMock(\''+m.id+'\')">Delete</button>':'')+'</div></div>'}).join('')+'</div></div>';
}
function __topicManagementHtml(){
  var s=__topicSummary();
  return '<div class="topicMgmtWrap"><div class="topicAddPanel"><div class="topicAddCard"><h3>Add FR topic</h3><p>Add each syllabus area you want to track. Use 50% while studying it, then mark it Completed when finished.</p><div class="topicAddRow"><input id="newTopicName" maxlength="140" placeholder="e.g. IAS 16 Property, plant and equipment"><button class="portalBtn primary" onclick="addProgressTopic()">Add topic</button></div></div><div class="schemaBox">Overall progress: '+s.percent+'%\\nCompleted: '+s.done+'\\n50% done: '+s.half+'\\nNot started: '+s.notStarted+'</div></div><div class="topicListPanel">'+
  (__hostedTopics.length?__hostedTopics.map(function(t){var p=Number(t.progress)||0;return '<div class="topicRow"><div><div class="topicName">'+__esc(t.title)+'</div><div class="topicStatus">'+(p===100?'Completed':p===50?'Half complete':'Not started')+' · '+p+'%</div></div><label class="topicCheck"><input type="checkbox" '+(p===50?'checked':'')+' onchange="setTopicProgress('+t.id+',this.checked?50:0)">50%</label><label class="topicCheck"><input type="checkbox" '+(p===100?'checked':'')+' onchange="setTopicProgress('+t.id+',this.checked?100:0)">Completed</label><button class="topicDelete" onclick="deleteProgressTopic('+t.id+')">Delete</button></div>'}).join(''):'<div class="emptyState">No topics yet. Add your first FR topic on the left.</div>')+
  '</div></div>';
}
function portalManagementV8(){
  if(!__isHostedAdmin())return '<div class="portalView managementPage"><div class="accessDenied"><div><h2>Management unavailable</h2><p>This area is restricted to the administrator account.</p></div></div></div>';
  return '<div class="portalView managementPage"><div class="pageHead"><h2>Management Center</h2><div class="managementTabs"><button class="managementTab '+(__managementTab==='mocks'?'active':'')+'" onclick="__managementTab=\'mocks\';renderPortalContent()">Mock Library</button><button class="managementTab '+(__managementTab==='topics'?'active':'')+'" onclick="__managementTab=\'topics\';renderPortalContent()">Progress Topics</button></div></div>'+(__managementTab==='topics'?__topicManagementHtml():__mockManagementHtml())+'</div>';
}
function toggleProfilePopover(ev){
  if(ev)ev.stopPropagation();
  var pop=document.getElementById('profilePopover');if(!pop)return;
  pop.classList.toggle('open');
}
function closeProfilePopover(){var pop=document.getElementById('profilePopover');if(pop)pop.classList.remove('open')}
function openSettingsFromProfile(){closeProfilePopover();showPortalView('settings')}
function __installProfilePopover(){
  var u=window.__HOSTED_F7_USER__||{};
  var btn=document.getElementById('profileTopButton');if(btn)btn.setAttribute('onclick','toggleProfilePopover(event)');
  var old=document.getElementById('profilePopover');if(old)old.remove();
  var pop=document.createElement('div');pop.id='profilePopover';pop.className='profilePopover';
  var initials=((u.displayName||u.username||'J').split(/\\s+/).map(function(x){return x[0]||''}).join('').slice(0,2)||'J').toUpperCase();
  var avatarStyle=u.avatar?"background-image:url('"+String(u.avatar).replace(/'/g,'%27')+"');color:transparent":'';
  pop.innerHTML='<div class="profilePopHead"><div class="profileAvatar pop" style="'+avatarStyle+'">'+__esc(initials)+'</div><div><div class="profilePopName">'+__esc(u.displayName||u.username)+'</div><div class="profilePopMail">'+__esc(u.email||'')+'</div><div class="profilePopStatus"><span class="profilePopChip">'+(u.googleLinked?'Google connected':'Fallback login')+'</span>'+(u.role==='admin'?'<span class="profilePopChip">Administrator</span>':'')+'</div></div></div><div class="profilePopMenu"><button class="profilePopItem" onclick="openSettingsFromProfile()">Settings <span>›</span></button><button class="profilePopItem danger" onclick="portalLogout()">Sign out <span>↗</span></button></div>';
  document.querySelector('.portalMain').appendChild(pop);
  document.addEventListener('click',function(e){if(!pop.contains(e.target)&&!(btn&&btn.contains(e.target)))closeProfilePopover()});
  document.addEventListener('keydown',function(e){if(e.key==='Escape')closeProfilePopover()});
}
function __renderHostedPortal(){
  var C=document.getElementById('portalContent');if(!C)return;
  if(portalView==='overview')C.innerHTML=portalOverviewV8();
  else if(portalView==='mocks')C.innerHTML=portalMocks();
  else if(portalView==='history')C.innerHTML=portalHistory();
  else if(portalView==='retests')C.innerHTML=portalRetests();
  else if(portalView==='analytics')C.innerHTML=portalAnalytics();
  else if(portalView==='management')C.innerHTML=portalManagementV8();
  else if(portalView==='settings')C.innerHTML=portalProfile();
  else C.innerHTML=portalOverviewV8();
  var root=C.querySelector('.portalView');if(root){root.classList.remove('portal-enter');void root.offsetWidth;root.classList.add('portal-enter')}
}
function __showHostedView(view){
  if(view==='management'&&!__isHostedAdmin())view='overview';
  portalView=view;
  qsa('.portalNavBtn').forEach(function(b){b.classList.toggle('active',b.dataset.pview===view)});
  var map={overview:['Dashboard','Financial Reporting practice overview'],mocks:['Mock Exams','Launch, resume and review exam-standard practice papers'],history:['Test History','Completed mocks and objective results'],retests:['Retests','Reattempt unresolved objective-test weaknesses'],analytics:['Analytics','Performance trends and section-level accuracy'],management:['Management','Mocks and syllabus progress controls'],settings:['Settings','Account, email, password and profile picture']};
  var meta=map[view]||map.overview;
  document.getElementById('portalTitle').textContent=meta[0];document.getElementById('portalSub').textContent=meta[1];
  document.getElementById('portalContent').classList.toggle('scrollView',['management','settings','mocks'].includes(view));
  closeProfilePopover();__renderHostedPortal();
}

window.addEventListener('load',function(){
  try{
    __applyHostedProfile(window.__HOSTED_F7_USER__);
    showPortalView=__showHostedView;
    renderPortalContent=__renderHostedPortal;
    portalManagement=portalManagementV8;
    portalOverviewV7=portalOverviewV8;
    var oldProfileNav=document.querySelector('[data-pview="profile"]');if(oldProfileNav)oldProfileNav.remove();
    var mg=document.querySelector('[data-pview="management"]');if(mg)mg.style.display=__isHostedAdmin()?'':'none';
    __installProfilePopover();
    __loadTopics(false);
    var login=document.getElementById('loginView'),dash=document.getElementById('dashboardView');
    if(login)login.classList.add('hiddenPortal');if(dash)dash.classList.remove('hiddenPortal');
    showPortalView('overview');__loadTopics(true);
    portalLogout=function(){fetch('/logout',{method:'POST',credentials:'same-origin'}).finally(function(){location.href='/login'})};
    googleSignInInfo=function(){location.href='/auth/google'};
    saveProfile=async function(){try{await __saveHostedProfile();var x=document.getElementById('profileSaved');if(x){x.textContent='Saved';setTimeout(function(){if(x)x.textContent=''},1500)}if(typeof toast==='function')toast('Profile saved.')}catch(e){if(typeof toast==='function')toast(e.message);else alert(e.message)}};
    changeProfilePicture=function(input){var f=input.files&&input.files[0];if(!f)return;if(f.size>2000000){if(typeof toast==='function')toast('Choose an image under 2 MB.');input.value='';return}var r=new FileReader();r.onload=async function(){try{await __saveHostedProfile({avatar:String(r.result||'')});if(typeof renderPortalContent==='function')renderPortalContent();}catch(e){if(typeof toast==='function')toast(e.message)}};r.readAsDataURL(f)};
  }catch(e){console.error('Hosted FR initialization failed',e)}
});
</script>
""".replace("__PROFILE__", profile)
    return html.replace("</body>", patch + "\n</body>")

@app.route("/")
@login_required
def portal():
    return Response(portal_html_for(current_user()), mimetype="text/html")

@app.route("/fr/")
def old_fr_redirect():
    return redirect(url_for("portal"))

@app.route("/health")
def health():
    return {"ok":True,"service":"jay-acca-fr-portal","google_oauth_configured":google_configured()}

purge_legacy_f6_f8_data()
init_db()

if __name__ == "__main__":
    port = int(os.getenv("SERVER_PORT", os.getenv("PORT", "5000")))
    app.run(host="0.0.0.0", port=port, debug=False)
