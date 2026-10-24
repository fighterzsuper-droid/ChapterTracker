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

@app.after_request
def security_headers(response):
    # Browser-level hardening. Note: ordinary websites cannot prevent an
    # external OS screenshot/recorder while the page is visibly focused.
    response.headers["Permissions-Policy"] = "display-capture=(), camera=(), microphone=()"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'none'; object-src 'none'; base-uri 'self'; "
        "form-action 'self' https://accounts.google.com"
    )
    return response

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

def user_public(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "displayName": row["display_name"],
        "avatar": row["avatar"] or row["google_picture"] or "",
        "googleLinked": bool(row["google_sub"]),
        "role": "admin",
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

def portal_html_for(user):
    try:
        raw = b"".join(path.read_bytes() for path in FR_PORTAL_PARTS)
        html = gzip.decompress(raw).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError):
        abort(503)

    profile = json.dumps(user_public(user), ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("</head>", """<style>
#loginView{display:none!important}
#capturePrivacyShield{position:fixed;inset:0;z-index:2147483646;background:#0d2941;color:#fff;display:none;align-items:center;justify-content:center;text-align:center;font-family:Arial,Helvetica,sans-serif}
#capturePrivacyShield.active{display:flex!important}
#capturePrivacyShield .shieldCard{max-width:520px;padding:28px 32px;border:1px solid rgba(255,255,255,.25);border-radius:14px;background:rgba(9,35,55,.96);box-shadow:0 24px 70px rgba(0,0,0,.35)}
#capturePrivacyShield h2{margin:0 0 8px;font-size:24px}
#capturePrivacyShield p{margin:0;color:#d8e8f4;line-height:1.5}
@media print{body>*{display:none!important}body:after{content:"Printing disabled for this protected FR portal.";display:block!important;padding:40px;font:700 20px Arial;color:#111}}
</style></head>""")
    patch = r"""
<script>
window.__HOSTED_F7_USER__=__PROFILE__;
function __applyHostedProfile(p){
  try{
    if(typeof portalMeta==='undefined')return;
    var prev=(portalMeta.users||{})[p.username]||{};
    portalMeta.users={};
    portalMeta.users[p.username]=Object.assign({},prev,{username:p.username,displayName:p.displayName,email:p.email,avatar:p.avatar||'',googleLinked:!!p.googleLinked,role:'admin',passwordHash:''});
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
  window.__HOSTED_F7_USER__=body;__applyHostedProfile(body);return body;
}

function __installCaptureProtection(){
  var shield=document.getElementById('capturePrivacyShield');
  if(!shield){
    shield=document.createElement('div');
    shield.id='capturePrivacyShield';
    shield.innerHTML='<div class="shieldCard"><h2>Protected content hidden</h2><p>Return to this tab to continue. The portal hides exam content whenever the tab is minimized, switched away from, or the browser window loses focus. Browser pages cannot block OS-level screenshots while content is actively visible.</p></div>';
    document.body.appendChild(shield);
  }
  function protect(){
    shield.classList.add('active');
    document.documentElement.style.background='#0d2941';
  }
  function reveal(){
    if(document.visibilityState==='visible' && document.hasFocus()) shield.classList.remove('active');
  }
  document.addEventListener('visibilitychange',function(){document.hidden?protect():setTimeout(reveal,40)});
  window.addEventListener('blur',protect,true);
  window.addEventListener('focus',function(){setTimeout(reveal,40)},true);
  window.addEventListener('beforeprint',protect);
  window.addEventListener('afterprint',reveal);
  document.addEventListener('contextmenu',function(e){e.preventDefault()});
  document.addEventListener('keydown',function(e){
    var k=String(e.key||'').toLowerCase();
    var printShortcut=(e.ctrlKey||e.metaKey)&&k==='p';
    var saveShortcut=(e.ctrlKey||e.metaKey)&&k==='s';
    var devShortcut=(e.ctrlKey||e.metaKey)&&e.shiftKey&&(k==='i'||k==='j'||k==='c');
    var printScreen=k==='printscreen';
    if(printShortcut||saveShortcut||devShortcut||printScreen){
      e.preventDefault();e.stopPropagation();protect();
      setTimeout(reveal,900);
      if(typeof toast==='function') toast('Capture/print shortcut blocked where supported by the browser.');
      return false;
    }
  },true);
  if(document.hidden || !document.hasFocus()) protect(); else reveal();
}

window.addEventListener('load',function(){
  try{
    __applyHostedProfile(window.__HOSTED_F7_USER__);
    __installCaptureProtection();
    var login=document.getElementById('loginView'),dash=document.getElementById('dashboardView');
    if(login)login.classList.add('hiddenPortal');if(dash)dash.classList.remove('hiddenPortal');
    if(typeof showDashboard==='function')showDashboard('overview');else if(typeof showPortalView==='function')showPortalView('overview');
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
