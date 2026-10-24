import gzip
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("AA_DB_PATH", str(BASE_DIR / "aa_hub.db")))
FR_PORTAL_PARTS = [BASE_DIR / f"fr_portal_v7.gz.part{i}" for i in range(4)]

app = Flask(__name__)
# Sessions are secret even when an operator has not yet configured the key.
# Set a permanent FLASK_SECRET_KEY in the Bot-Hosting environment before launch.
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=34 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("HUB_ALLOW_HTTP") != "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

CHAPTERS = [
    "Introduction to Assurance",
    "Rules and Regulation",
    "Corporate Governance",
    "Ethics and Acceptance",
    "Risk",
    "Planning",
    "Evidence",
    "Systems and Controls",
    "Internal Audit",
    "Procedures",
    "Completion and Review",
    "Reporting",
    "Summary of Key ISAs",
    "Financial Reporting Revision",
    "Employability and Technology Skills",
]

FULL_TEST = [
    {
        "position": 1, "type": "mcq", "marks": 2,
        "prompt": "The shareholders of Apex Co appoint an external auditor. What is the main value of the audit to those shareholders?",
        "options": [
            "It guarantees that every transaction is correct.",
            "It provides independent reasonable assurance over the financial statements prepared by management.",
            "It transfers responsibility for preparing the financial statements to the auditor.",
            "It guarantees that the company will remain profitable."
        ], "correct_index": 1
    },
    {
        "position": 2, "type": "mcq", "marks": 2,
        "prompt": "Which situation best illustrates the audit expectation gap?",
        "options": [
            "Users expect auditors to obtain reasonable assurance.",
            "Users believe an audit guarantees complete accuracy and detection of every fraud.",
            "Directors understand that they remain responsible for the financial statements.",
            "Auditors use professional judgement when obtaining evidence."
        ], "correct_index": 1
    },
    {
        "position": 3, "type": "mcq", "marks": 2,
        "prompt": "Which statement about a statutory financial statement audit is correct?",
        "options": [
            "It provides absolute assurance.",
            "It normally provides limited assurance using negative wording.",
            "It provides reasonable assurance and a positive-form opinion.",
            "It provides no assurance because management prepares the statements."
        ], "correct_index": 2
    },
    {
        "position": 4, "type": "mcq", "marks": 2,
        "prompt": "A lender requests assurance over a 12-month cash-flow forecast. Which criteria would be most appropriate?",
        "options": [
            "The auditor's personal expectations only.",
            "An appropriate basis of preparation together with reasonable, supportable forecast assumptions.",
            "The company's current share price.",
            "Any accounting standard, even if unrelated to forecasts."
        ], "correct_index": 1,
        "weakness_tag": "suitable-criteria"
    },
    {
        "position": 5, "type": "mcq", "marks": 2,
        "prompt": "Which combination is most consistent with a limited assurance review engagement?",
        "options": [
            "Extensive testing and a positive-form opinion.",
            "Mainly enquiry and analytical procedures with a negative-form conclusion.",
            "100% testing and an absolute guarantee.",
            "No evidence gathering."
        ], "correct_index": 1
    },
    {
        "position": 6, "type": "mcq", "marks": 2,
        "prompt": "A donor asks for assurance over a charity's report showing how grant money was allocated. What is the subject matter information?",
        "options": [
            "The assurance practitioner's independence policy.",
            "The report showing how the grant money was allocated.",
            "The audit fee.",
            "The donor's bank statement."
        ], "correct_index": 1
    },
    {
        "position": 7, "type": "mcq", "marks": 2,
        "prompt": "For assurance over the charity's grant-allocation process, which criteria are most suitable?",
        "options": [
            "The charity's grant policy, donor agreement and relevant grant rules.",
            "A stock-exchange rule unrelated to grant allocation.",
            "The practitioner's personal preference.",
            "The prior-year audit opinion."
        ], "correct_index": 0,
        "weakness_tag": "suitable-criteria"
    },
    {
        "position": 8, "type": "mcq", "marks": 2,
        "prompt": "Which of the following is NOT one of the five formal elements of an assurance engagement?",
        "options": [
            "A three-party relationship.",
            "Suitable criteria.",
            "The practitioner's independence.",
            "Sufficient appropriate evidence."
        ], "correct_index": 2,
        "weakness_tag": "five-elements"
    },
    {
        "position": 9, "type": "mcq", "marks": 2,
        "prompt": "Why can a financial statement audit not provide absolute assurance?",
        "options": [
            "Auditors never obtain external evidence.",
            "Management selects the audit opinion.",
            "Audits have inherent limitations, including judgement, sampling and evidence that is persuasive rather than conclusive.",
            "Audits are always voluntary."
        ], "correct_index": 2
    },
    {
        "position": 10, "type": "mcq", "marks": 2,
        "prompt": "Which statement best explains stewardship and accountability?",
        "options": [
            "Shareholders manage the company while directors audit it.",
            "Directors manage resources on behalf of shareholders and are accountable for how those resources are used.",
            "The external auditor becomes responsible for running the company.",
            "Banks prepare the financial statements for shareholders."
        ], "correct_index": 1
    },
    {
        "position": 11, "type": "written", "marks": 5,
        "prompt": "Beacon Co publishes a carbon sustainability report. A lender asks for independent assurance over that report. Identify and explain the five elements of an assurance engagement and apply each element to this scenario."
    },
    {
        "position": 12, "type": "written", "marks": 5,
        "prompt": "Falcon Co is considering either a full audit or a review engagement. Explain FIVE differences between reasonable assurance provided by an audit and limited assurance provided by a review."
    },
]

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS chapter_progress (
        chapter INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        notes_created INTEGER NOT NULL DEFAULT 0,
        taught INTEGER NOT NULL DEFAULT 0,
        tested INTEGER NOT NULL DEFAULT 0,
        marked INTEGER NOT NULL DEFAULT 0,
        corrected INTEGER NOT NULL DEFAULT 0,
        retested INTEGER NOT NULL DEFAULT 0,
        applied INTEGER NOT NULL DEFAULT 0,
        latest_mark REAL,
        status TEXT NOT NULL DEFAULT 'Not Started'
    );

    CREATE TABLE IF NOT EXISTS assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL UNIQUE,
        chapter INTEGER NOT NULL,
        max_marks REAL NOT NULL,
        kind TEXT NOT NULL DEFAULT 'quiz',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        qtype TEXT NOT NULL,
        marks REAL NOT NULL,
        prompt TEXT NOT NULL,
        options_json TEXT,
        correct_index INTEGER,
        weakness_tag TEXT,
        FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id INTEGER NOT NULL,
        submitted_at TEXT NOT NULL,
        mcq_score REAL NOT NULL DEFAULT 0,
        written_score REAL,
        total_score REAL,
        max_marks REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending written marking',
        source TEXT NOT NULL DEFAULT 'site',
        FOREIGN KEY (assessment_id) REFERENCES assessments(id)
    );

    CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        answer_text TEXT,
        selected_index INTEGER,
        is_correct INTEGER,
        marks_awarded REAL,
        FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE,
        FOREIGN KEY (question_id) REFERENCES questions(id)
    );

    CREATE TABLE IF NOT EXISTS weaknesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chapter INTEGER NOT NULL,
        title TEXT NOT NULL UNIQUE,
        details TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Open - awaiting retest',
        weakness_tag TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # Do not rewrite real progress when the server restarts.
    first_chapter_is_new = conn.execute("SELECT 1 FROM chapter_progress WHERE chapter=1").fetchone() is None
    for i, name in enumerate(CHAPTERS, start=1):
        conn.execute(
            """INSERT OR IGNORE INTO chapter_progress
            (chapter, name, notes_created, status)
            VALUES (?, ?, ?, ?)""",
            (i, name, 1 if i <= 7 else 0, "Not Started")
        )

    if first_chapter_is_new:
        # Migrate the starter baseline once only; never reset completed work.
        conn.execute(
            """UPDATE chapter_progress
            SET notes_created=1, taught=1, tested=1, marked=1, corrected=1,
                retested=0, applied=0, latest_mark=76.9, status='In Progress'
            WHERE chapter=1"""
        )

    prior = conn.execute("SELECT id FROM assessments WHERE title=?", ("Chapter 1 Quiz 1 (Prior)",)).fetchone()
    if not prior:
        cur = conn.execute(
            "INSERT INTO assessments (title, chapter, max_marks, kind, active, created_at) VALUES (?,1,13,'quiz',0,?)",
            ("Chapter 1 Quiz 1 (Prior)", now_iso())
        )
        prior_id = cur.lastrowid
        conn.execute(
            """INSERT INTO attempts
            (assessment_id, submitted_at, mcq_score, written_score, total_score, max_marks, status, source)
            VALUES (?, ?, 10, 0, 10, 13, 'Marked - weaknesses open', 'imported')""",
            (prior_id, "2026-09-25T00:00:00+00:00")
        )

    full = conn.execute("SELECT id FROM assessments WHERE title=?", ("Chapter 1 Full Test — Introduction to Assurance",)).fetchone()
    if not full:
        cur = conn.execute(
            "INSERT INTO assessments (title, chapter, max_marks, kind, active, created_at) VALUES (?,1,30,'full test',1,?)",
            ("Chapter 1 Full Test — Introduction to Assurance", now_iso())
        )
        assessment_id = cur.lastrowid
        for q in FULL_TEST:
            conn.execute(
                """INSERT INTO questions
                (assessment_id, position, qtype, marks, prompt, options_json, correct_index, weakness_tag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    assessment_id, q["position"], q["type"], q["marks"], q["prompt"],
                    json.dumps(q.get("options")) if q.get("options") else None,
                    q.get("correct_index"), q.get("weakness_tag")
                )
            )

    weakness_rows = [
        (
            1,
            "Five assurance elements — formal element identification",
            "Distinguish the five formal assurance elements from other professional requirements such as practitioner independence.",
            "five-elements"
        ),
        (
            1,
            "Suitable criteria — scenario application",
            "Choose criteria that are appropriate to the subject matter. For a grant-allocation engagement, relevant grant rules, policies, agreements or legislation are suitable; an unrelated financial reporting framework is not.",
            "suitable-criteria"
        ),
    ]
    for chapter, title, details, tag in weakness_rows:
        conn.execute(
            "INSERT OR IGNORE INTO weaknesses (chapter, title, details, status, weakness_tag, created_at) VALUES (?, ?, ?, 'Open - awaiting retest', ?, ?)",
            (chapter, title, details, tag, now_iso())
        )

    conn.commit()
    conn.close()

@app.context_processor
def inject_globals():
    return {"app_name": "Jay's ACCA AA Exam Hub"}

@app.route("/")
def dashboard():
    conn = get_db()
    chapters = conn.execute("SELECT * FROM chapter_progress ORDER BY chapter").fetchall()
    attempts = conn.execute(
        """SELECT at.*, a.title, a.chapter
        FROM attempts at JOIN assessments a ON a.id=at.assessment_id
        ORDER BY at.id DESC LIMIT 5"""
    ).fetchall()
    open_weaknesses = conn.execute("SELECT COUNT(*) c FROM weaknesses WHERE status LIKE 'Open%'").fetchone()["c"]
    note_count = sum(int(c["notes_created"]) for c in chapters)
    complete_count = sum(1 for c in chapters if c["status"] == "Complete")
    avg = conn.execute("SELECT AVG((total_score/max_marks)*100.0) a FROM attempts WHERE total_score IS NOT NULL").fetchone()["a"]
    conn.close()
    return render_template(
        "dashboard.html",
        chapters=chapters,
        attempts=attempts,
        open_weaknesses=open_weaknesses,
        note_count=note_count,
        complete_count=complete_count,
        average=round(avg, 1) if avg is not None else None,
    )

@app.route("/chapters")
def chapters():
    conn = get_db()
    rows = conn.execute("SELECT * FROM chapter_progress ORDER BY chapter").fetchall()
    conn.close()
    return render_template("chapters.html", chapters=rows)

@app.route("/tests")
def tests():
    conn = get_db()
    rows = conn.execute("SELECT * FROM assessments WHERE active=1 ORDER BY chapter, id").fetchall()
    conn.close()
    return render_template("tests.html", tests=rows)

@app.route("/tests/<int:assessment_id>")
def take_test(assessment_id):
    conn = get_db()
    assessment = conn.execute("SELECT * FROM assessments WHERE id=? AND active=1", (assessment_id,)).fetchone()
    if not assessment:
        conn.close()
        abort(404)
    rows = conn.execute("SELECT * FROM questions WHERE assessment_id=? ORDER BY position", (assessment_id,)).fetchall()
    questions = []
    for row in rows:
        item = dict(row)
        item["options"] = json.loads(row["options_json"]) if row["options_json"] else []
        questions.append(item)
    conn.close()
    return render_template("take_test.html", assessment=assessment, questions=questions)

@app.post("/tests/<int:assessment_id>/submit")
def submit_test(assessment_id):
    conn = get_db()
    assessment = conn.execute("SELECT * FROM assessments WHERE id=? AND active=1", (assessment_id,)).fetchone()
    if not assessment:
        conn.close()
        abort(404)
    questions = conn.execute("SELECT * FROM questions WHERE assessment_id=? ORDER BY position", (assessment_id,)).fetchall()

    mcq_score = 0.0
    has_written = False
    cur = conn.execute(
        """INSERT INTO attempts
        (assessment_id, submitted_at, mcq_score, written_score, total_score, max_marks, status, source)
        VALUES (?, ?, 0, NULL, NULL, ?, 'Pending written marking', 'site')""",
        (assessment_id, now_iso(), assessment["max_marks"])
    )
    attempt_id = cur.lastrowid

    for q in questions:
        field = f"q_{q['id']}"
        if q["qtype"] == "mcq":
            raw = request.form.get(field, "")
            selected = int(raw) if raw.isdigit() else None
            correct = selected == q["correct_index"]
            awarded = float(q["marks"]) if correct else 0.0
            mcq_score += awarded
            conn.execute(
                """INSERT INTO answers
                (attempt_id, question_id, selected_index, is_correct, marks_awarded)
                VALUES (?, ?, ?, ?, ?)""",
                (attempt_id, q["id"], selected, 1 if correct else 0, awarded)
            )
        else:
            has_written = True
            text_answer = request.form.get(field, "").strip()
            conn.execute(
                """INSERT INTO answers
                (attempt_id, question_id, answer_text, is_correct, marks_awarded)
                VALUES (?, ?, ?, NULL, NULL)""",
                (attempt_id, q["id"], text_answer)
            )

    if has_written:
        status = "Pending written marking"
        total_score = None
    else:
        status = "Auto-marked"
        total_score = mcq_score

    conn.execute(
        "UPDATE attempts SET mcq_score=?, total_score=?, status=? WHERE id=?",
        (mcq_score, total_score, status, attempt_id)
    )
    conn.commit()
    conn.close()
    flash("Attempt submitted successfully.", "success")
    return redirect(url_for("attempt_result", attempt_id=attempt_id))

@app.route("/attempts")
def attempts():
    conn = get_db()
    rows = conn.execute(
        """SELECT at.*, a.title, a.chapter
        FROM attempts at JOIN assessments a ON a.id=at.assessment_id
        ORDER BY at.id DESC"""
    ).fetchall()
    conn.close()
    return render_template("history.html", attempts=rows)

@app.route("/attempts/<int:attempt_id>")
def attempt_result(attempt_id):
    conn = get_db()
    attempt = conn.execute(
        """SELECT at.*, a.title, a.chapter
        FROM attempts at JOIN assessments a ON a.id=at.assessment_id
        WHERE at.id=?""",
        (attempt_id,)
    ).fetchone()
    if not attempt:
        conn.close()
        abort(404)
    answers = conn.execute(
        """SELECT ans.*, q.position, q.qtype, q.marks, q.prompt, q.options_json, q.correct_index
        FROM answers ans JOIN questions q ON q.id=ans.question_id
        WHERE ans.attempt_id=? ORDER BY q.position""",
        (attempt_id,)
    ).fetchall()
    answer_items = []
    for row in answers:
        item = dict(row)
        item["options"] = json.loads(row["options_json"]) if row["options_json"] else []
        answer_items.append(item)
    conn.close()
    return render_template("attempt.html", attempt=attempt, answers=answer_items)

@app.route("/weaknesses")
def weaknesses():
    conn = get_db()
    rows = conn.execute("SELECT * FROM weaknesses ORDER BY CASE WHEN status LIKE 'Open%' THEN 0 ELSE 1 END, id DESC").fetchall()
    conn.close()
    return render_template("weaknesses.html", weaknesses=rows)


@app.route("/fr/")
def fr_portal():
    """Serve the self-contained FR/F7 portal behind the Study Hub login."""
    try:
        compressed = b"".join(path.read_bytes() for path in FR_PORTAL_PARTS)
        html = gzip.decompress(compressed).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError):
        abort(503)

    # Standalone v7 contains a local demo login. The hosted version already
    # sits behind security.py, so enter its dashboard directly and map logout
    # back to the Study Hub session.
    hosted_patch = """
<script>
window.addEventListener("load", function () {
  try {
    if (typeof portalSession !== "undefined") {
      portalSession = {username: "jay", name: "Jayakiran"};
    }
    const login = document.getElementById("loginView");
    const dash = document.getElementById("dashboardView");
    if (login) login.classList.add("hiddenPortal");
    if (dash) dash.classList.remove("hiddenPortal");
    if (typeof showDashboard === "function") showDashboard("overview");
    if (typeof portalLogout === "function") {
      portalLogout = function () {
        const form = document.createElement("form");
        form.method = "post";
        form.action = "/logout";
        document.body.appendChild(form);
        form.submit();
      };
    }
  } catch (error) {
    console.error("FR hosted-mode initialization failed", error);
  }
});
</script>
"""
    html = html.replace("</body>", hosted_patch + "\n</body>")
    return Response(html, mimetype="text/html")

@app.route("/health")
def health():
    return {"ok": True, "service": "jay-acca-aa-exam-hub"}

@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404

init_db()

from tx_hub import tx
app.register_blueprint(tx)
from study_time import study_time
app.register_blueprint(study_time)
from watcher import watcher
app.register_blueprint(watcher)
from board import board
app.register_blueprint(board)
from security import auth
app.register_blueprint(auth)
from restart_ui import restart_ui
app.register_blueprint(restart_ui)

if __name__ == "__main__":
    port = int(os.getenv("SERVER_PORT", os.getenv("PORT", "5000")))
    app.run(host="0.0.0.0", port=port, debug=False)
