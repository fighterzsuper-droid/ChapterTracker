"""Self Overview: server-backed study analytics in Kuwait local time.

This is a Flask Blueprint, not a second background process. The foreground
visibility signals are received by study_time.py; this module displays totals.
"""
import time
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from study_time import ZONE, connect, summary

watcher = Blueprint("watcher", __name__)


@watcher.get("/self-overview")
def self_overview():
    return render_template("self_overview.html")


def overview_snapshot(db, selected_day):
    now = datetime.now(ZONE)
    today = now.date()
    first = today - timedelta(days=6)
    aa = summary(db, "AA")
    tx = summary(db, "TX")

    hour_rows = db.execute(
        """SELECT subject, hour, SUM(seconds) AS seconds
           FROM study_hour WHERE day=?
           GROUP BY subject, hour""",
        (selected_day.isoformat(),),
    ).fetchall()
    hours = [{"hour": h, "AA": 0.0, "TX": 0.0} for h in range(24)]
    for row in hour_rows:
        if row["subject"] in ("AA", "TX"):
            hours[row["hour"]][row["subject"]] += round(row["seconds"], 1)

    day_rows = db.execute(
        """SELECT subject, day, SUM(seconds) AS seconds
           FROM study_day WHERE day>=? AND day<=?
           GROUP BY subject, day""",
        (first.isoformat(), today.isoformat()),
    ).fetchall()
    days = [
        {
            "day": (first + timedelta(days=i)).isoformat(),
            "AA": 0.0,
            "TX": 0.0,
        } for i in range(7)
    ]
    index = {v["day"]: v for v in days}
    for row in day_rows:
        if row["subject"] in ("AA", "TX") and row["day"] in index:
            index[row["day"]][row["subject"]] += round(row["seconds"], 1)

    selected_counts = db.execute(
        """SELECT subject, SUM(seconds) AS seconds FROM study_day
           WHERE day=? GROUP BY subject""", (selected_day.isoformat(),)
    ).fetchall()
    selected = {"AA": 0.0, "TX": 0.0}
    for row in selected_counts:
        if row["subject"] in selected:
            selected[row["subject"]] = round(row["seconds"], 1)

    return {
        "timezone": "Asia/Kuwait",
        "server_now_ms": round(time.time() * 1000),
        "today": today.isoformat(),
        "selected_day": selected_day.isoformat(),
        "today_totals": {
            "AA": aa["today_seconds"],
            "TX": tx["today_seconds"],
        },
        "selected_totals": selected,
        "week_totals": {"AA": aa["week_seconds"], "TX": tx["week_seconds"]},
        "lifetime_totals": {"AA": aa["total_seconds"], "TX": tx["total_seconds"]},
        "hours": hours,
        "days": days,
    }


@watcher.get("/api/self-overview")
def overview_api():
    raw_date = request.args.get("date", "")
    today = datetime.now(ZONE).date()
    try:
        selected = date.fromisoformat(raw_date) if raw_date else today
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date"}), 400
    if selected > today:
        return jsonify({"error": "Future dates are not available"}), 400

    with connect() as db:
        data = overview_snapshot(db, selected)
    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store"
    return response
