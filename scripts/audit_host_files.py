"""Inspect a mixed CricEdge/Study Hub folder without modifying any files.

On Bot-Hosting, choose the folder shown under Files / cogs:
    python scripts/audit_host_files.py --root .
No deletion is performed by this script.
"""
import argparse
import json
from pathlib import Path

STUDY_FILES = {
    "app.py", "tx_hub.py", "restart_ui.py", "study_time.py", "watcher.py",
    "security.py", "requirements.txt", ".gitignore", "README.md",
    "JAY_STUDY_HUB_REBUILD_REQUIREMENTS.md"
}
STUDY_FOLDERS = {
    "templates", "static", "tests", ".github", ".git", "scripts", "deployment",
    "backups", "server_backups"
}
PRESERVE_PRIVATE = {
    "aa_hub.db", "tx_hub.db", "study_time.db", ".env",
    ".env.production", ".env.local", "config.json",
}
LEGACY_CANDIDATES = {
    "Agent.py", "app2.py", "bot.py", "players.db", "match_updates.py",
    "news_manager.py", "points_table.py", "purse_slots.py",
    "retention_poster.py", "schedule.py", "scorecard.py",
    "sold_players.py", "squads.py", "teams.py", "trades.py",
    "unsold_players.py",
}


def classify(name, is_directory=False):
    if name in PRESERVE_PRIVATE or name.endswith(("-journal", "-wal", "-shm")):
        return "PRESERVE PRIVATE DATA / CONFIG"
    if name in STUDY_FOLDERS and is_directory:
        return "STUDY HUB / DEPLOYMENT SUPPORT"
    if name in STUDY_FILES and not is_directory:
        return "STUDY HUB / DEPLOYMENT SUPPORT"
    if name in LEGACY_CANDIDATES and not is_directory:
        return "CANDIDATE LEGACY — VERIFY BEFORE DELETION"
    if name.startswith("."):
        return "HIDDEN — DO NOT DELETE WITHOUT INSPECTION"
    return "UNKNOWN — INSPECT MANUALLY"


def audit(root):
    return [{
        "name": p.name,
        "kind": "directory" if p.is_dir() else "file",
        "classification": classify(p.name, p.is_dir()),
    } for p in sorted(root.iterdir(), key=lambda x: x.name.casefold())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("The selected root is not a directory")
    rows = audit(root)
    if args.json:
        print(json.dumps({"root": str(root), "entries": rows}, indent=2))
    else:
        print("AUDIT ONLY — NOTHING WILL BE DELETED\nDirectory:", root)
        for row in rows:
            print(row["classification"].ljust(47), row["kind"].ljust(9), row["name"])
        print("\nBack up .db files and .env before removing any CricEdge components.")
        print("Only remove files after verifying no running process imports them.")


if __name__ == "__main__":
    main()
