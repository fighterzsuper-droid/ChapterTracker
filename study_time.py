"""Conservative, server-timed foreground-tab study tracking for AA and TX.

This measures focused-tab time, NOT verified concentration. No idle-click detector:
reading a page without interacting continues to count while it is foregrounded.
"""
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, time as clock_time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request

study_time = Blueprint("study_time", __name__, url_prefix="/api/study-time")
DB = Path(os.getenv("STUDY_TIME_DB_PATH", str(Path(__file__).resolve().parent / "study_time.db")))
try:
    ZONE = ZoneInfo("Asia/Kuwait")
except Exception:
    # Kuwait has a fixed UTC+03:00 offset (no daylight-saving clock changes).
    ZONE = timezone(timedelta(hours=3))
MAX_HEARTBEAT_GAP = 16.0  # Clients heartbeat every 10s; long/sleep gaps earn zero.
TOKEN_PATTERN = re.compile(r"^[a-f0-9]{32}$")
SUBJECTS = {"AA", "TX"}


def connect():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS study_day (
                subject TEXT NOT NULL,
                day TEXT NOT NULL,
                seconds REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (subject, day)
            );
            CREATE TABLE IF NOT EXISTS study_hour (
                subject TEXT NOT NULL,
                day TEXT NOT NULL,
                hour INTEGER NOT NULL CHECK(hour BETWEEN 0 AND 23),
                seconds REAL NOT NULL DEFAULT 0,
                PRIMARY KEY(subject, day, hour)
            );
            CREATE TABLE IF NOT EXISTS study_lease (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                tab_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                last_seen REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS study_tab_sequence (
                tab_id TEXT PRIMARY KEY,
                last_seq INTEGER NOT NULL,
                updated REAL NOT NULL
            );
        """)


def add_seconds(db, subject, first, last):
    """Persist verified time in both local-day and local-hour buckets.

    Split each interval at Kuwait clock-hour boundaries, so charts and totals
    agree even when studying across 11:59 PM / midnight.
    """
    while first < last:
        local = datetime.fromtimestamp(first, ZONE)
        hour_start = local.replace(minute=0, second=0, microsecond=0)
        next_hour = (hour_start + timedelta(hours=1)).timestamp()
        end = min(last, next_hour)
        seconds = end - first
        if seconds <= 0:
            break
        day = local.date().isoformat()
        db.execute(
            """INSERT INTO study_day(subject,day,seconds) VALUES (?,?,?)
               ON CONFLICT(subject,day) DO UPDATE SET seconds = seconds + excluded.seconds""",
            (subject, day, seconds),
        )
        db.execute(
            """INSERT INTO study_hour(subject,day,hour,seconds) VALUES (?,?,?,?)
               ON CONFLICT(subject,day,hour) DO UPDATE SET seconds = seconds + excluded.seconds""",
            (subject, day, local.hour, seconds),
        )
        first = end


def summary(db, subject):
    today = datetime.now(ZONE).date()
    week_start = (today - timedelta(days=6)).isoformat()
    row = db.execute(
        """SELECT COALESCE(SUM(CASE WHEN day=? THEN seconds ELSE 0 END),0) AS today,
                  COALESCE(SUM(CASE WHEN day>=? THEN seconds ELSE 0 END),0) AS week,
                  COALESCE(SUM(seconds),0) AS total
           FROM study_day WHERE subject=?""",
        (today.isoformat(), week_start, subject),
    ).fetchone()
    return {
        "subject": subject,
        "day": today.isoformat(),
        "timezone": "Asia/Kuwait",
        "today_seconds": round(row["today"], 1),
        "week_seconds": round(row["week"], 1),
        "total_seconds": round(row["total"], 1),
    }


@study_time.get("/stats")
def stats():
    subject = request.args.get("subject", "").upper()
    if subject not in SUBJECTS:
        return jsonify({"error": "Invalid subject"}), 400
    with connect() as db:
        result = summary(db, subject)
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response


@study_time.post("/pulse")
def pulse():
    # A cross-site form cannot post JSON here; browsers do not grant cross-site
    # fetch access without CORS. This is NOT user authentication.
    if request.mimetype != "application/json":
        return jsonify({"error": "JSON required"}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    subject = payload.get("subject")
    tab_id = payload.get("tab_id")
    seq = payload.get("seq")
    active = payload.get("active")
    if (subject not in SUBJECTS or not isinstance(tab_id, str)
            or not TOKEN_PATTERN.fullmatch(tab_id)
            or type(seq) is not int or not 0 < seq < 2147483647
            or type(active) is not bool):
        return jsonify({"error": "Invalid study timer payload"}), 400

    now = time.time()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        last_seq = db.execute(
            "SELECT last_seq FROM study_tab_sequence WHERE tab_id=?", (tab_id,)
        ).fetchone()
        if last_seq is not None and seq <= last_seq["last_seq"]:
            data = summary(db, subject)
            data["accepted"] = False
            db.commit()
            return jsonify(data)

        db.execute(
            """INSERT INTO study_tab_sequence(tab_id,last_seq,updated) VALUES (?,?,?)
               ON CONFLICT(tab_id) DO UPDATE SET
                  last_seq=excluded.last_seq, updated=excluded.updated""",
            (tab_id, seq, now),
        )

        current = db.execute("SELECT * FROM study_lease WHERE id=1").fetchone()
        if current is not None and current["tab_id"] == tab_id:
            elapsed = now - current["last_seen"]
            # Count only short, verified gaps; no catch-up after offline/sleep.
            if 0 <= elapsed <= MAX_HEARTBEAT_GAP:
                add_seconds(db, current["subject"], current["last_seen"], now)
            if active:
                db.execute(
                    "UPDATE study_lease SET subject=?,last_seen=? WHERE id=1",
                    (subject, now),
                )
            else:
                db.execute("DELETE FROM study_lease WHERE id=1")
        elif active:
            # Only one tab/device can hold the lease at a time. When a new tab
            # takes over, unverified time after the old tab's last pulse is lost.
            db.execute(
                """INSERT INTO study_lease(id,tab_id,subject,last_seen)
                   VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET
                   tab_id=excluded.tab_id, subject=excluded.subject,
                   last_seen=excluded.last_seen""",
                (tab_id, subject, now),
            )

        # Inactive events from other tabs must never stop the current lease.
        data = summary(db, subject)
        data["accepted"] = True
        db.commit()

    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store"
    return response


initialize()
