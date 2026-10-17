# Jay Study Hub — clean Bot-Hosting setup

## What this provides
A standalone Flask website for Jayakiran, separate from CricEdge and the brother's project:
- AA/F8 progress, exam-standard assessment attempts, results, weakness log
- TX/F6 syllabus/topics, notes, goals, diagnostics, results and weaknesses
- Focus-only timer that credits visible/focused study tabs without clicks
- Self Overview at /self-overview, live Kuwait clock and hour/day graphs
- Password-protected pages and JSON APIs
- SQLite stores separated by subject, with configurable persistent paths

## IMPORTANT: before touching Files / cogs
1. **Download a Bot-Hosting full backup and separately save the existing .env privately.**
2. Preserve aa_hub.db, tx_hub.db and any study_time.db. Never wipe these
   because the current site's existing student history may be irreplaceable.
3. The GitHub repo does **not** necessarily contain the server's current files.
   Git pull may leave old CricEdge files in place.
4. If the folder contains another actively running bot, stop that program and
   verify the Study Hub deployment is configured separately.
5. The provided scripts/audit_host_files.py lists candidate legacy files but
   intentionally does NOT delete them.

## Host environment configuration (Bot-Hosting Environment tab)
Set:
- `HUB_ACCESS_PASSWORD`: a strong unique secret for your personal dashboard.
  Alternatively set `HUB_PASSWORD_HASH` using Werkzeug's password hashing.
- `FLASK_SECRET_KEY`: a long random secret, kept unchanged between restarts.
- `AA_DB_PATH`: optional absolute persistent path for AA database.
- `TX_DB_PATH`: optional absolute persistent path for TX database.
- `STUDY_TIME_DB_PATH`: optional absolute persistent path for study-time database.

**Never commit real values into GitHub or paste the .env into ChatGPT.**
On public HTTPS hosting, secure session cookies are required. For localhost-only
development set `HUB_ALLOW_HTTP=1` to test sign-in via http://127.0.0.1.

If the login password is missing, the application deliberately displays a
setup-required screen instead of exposing student records.

## Deployment after reviewing backups
1. Prepare a clean folder under the hosting's Python deployment with only the
   runtime files listed in deployment/manifest.json, plus your preserved .env
   and existing study databases. Keep templates/ and static/ subdirectories.
2. In the terminal run `python -m pip install -r requirements.txt`.
3. Configure Python startup to run `python app.py` from that clean folder.
   **Do not** run `watcher.py` separately. It is imported by app.py.
4. Restart the host and open /health, /login and /self-overview.
5. Sign in and verify AA and TX pages, chapter and quiz history.
6. Open a study page for 30s, then switch tabs for 30s; verify only focused
   seconds count on the Self Overview graph.
7. Check the host's volume persists your databases after a routine restart.
8. After verification, quarantine/delete old CricEdge files in the *old*
   mixed directory, excluding private study databases and secrets.
9. Keep the rollback backup off the hosting service.

## Backup/audit commands (from the folder actually containing databases)

    python scripts/audit_host_files.py --root .
    python scripts/backup_study_data.py --root . --output ../jay-study-backup.zip

The second command excludes .env on purpose. Download its output, confirm
it contains AA/TX records, and make a separate private environment backup.

## Not yet implemented
- Automatic import/synchronisation from external Jotform and Google Sheets.
- Proof that the student read attentively rather than merely focused the tab.
- Tamper-resistant identity/device attestation; a private password helps,
  but authorised users can still create synthetic requests.
- Actual deletion/replacement on the live Bot-Hosting Files panel by ChatGPT
  without access to that hosting account.

The clean files are ready to deploy *after* the live databases are backed up.
