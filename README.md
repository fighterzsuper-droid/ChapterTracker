# Jay Study Hub — ACCA AA/F8 + TX/F6

Personal exam preparation website for **Jayakiran**, built with Python/Flask.
This repository contains only Study Hub code, not the old CricEdge cricket bot.

> **Deployment status:** This clean rebuild branch is intended for review and
> testing. It does **not** automatically delete or replace the existing files
> under Bot-Hosting > Files > cogs.

## Pages

| Section | URL | Purpose |
| --- | --- | --- |
| AA dashboard | `/` | Kaplan chapter progress and latest assessments |
| AA chapters | `/chapters` | Syllabus milestones |
| AA tests | `/tests` | Scenario-based questions and written answers |
| AA weakness log | `/weaknesses` | Unresolved topic weaknesses |
| AA assessment history | `/attempts` | Past answers and marking state |
| TX dashboard | `/tx/` | Taxation course progress |
| TX topics | `/tx/topics` | Chapter/part progression |
| TX notes | `/tx/notes/1A` etc. | Available revision notes |
| TX practice | `/tx/quiz` | Initial diagnostic |
| TX goals | `/tx/goals` | Daily tasks and study goals |
| TX history/weaknesses | `/tx/history`, `/tx/weaknesses` | Progress logs |
| Self Overview | `/self-overview` | Kuwait clock, hourly and 7-day focus graphs |
| Health check | `/health` | App up-status only |
| Sign in/out | `/login`, `/logout` | Private personal access |

## File layout

- `app.py`: entrypoint, AA pages, Flask configuration and blueprint registration.
- `tx_hub.py`: independent TX/F6 records and routes.
- `study_time.py`: server-validated focus heartbeat ledger and Kuwait hourly buckets.
- `watcher.py`: Self Overview charts and JSON API; **not** a separate bot process.
- `security.py`: private password login.
- `restart_ui.py`: optional administrator deployment restart integration.
- `static/`, `templates/`: responsive site presentation.
- `requirements.txt`: installed Python dependencies.
- `deployment/manifest.json`: exact runtime file list.
- `deployment/BOT_HOSTING_SETUP.md`: hosting setup, storage and restore procedures.
- `scripts/`: non-destructive inventory and SQLite-safe backup tools.
- `tests/`: focused time, privacy, and progress-preservation tests.

## Run locally

1. Install Python 3.11+ and `python -m pip install -r requirements.txt`.
2. Set `HUB_ACCESS_PASSWORD` to your own strong password.
3. Set `FLASK_SECRET_KEY` to a random, persistent secret.
4. For local HTTP only set `HUB_ALLOW_HTTP=1`.
5. Run `python app.py` and open `http://127.0.0.1:5000/login`.
6. Execute tests with `python -m unittest discover -s tests -v`.

## Bot-Hosting

Keep the Python startup file `app.py` and place the entire runtime file list
from `deployment/manifest.json` in the same clean working directory, with
`templates/` and `static/` retaining their folder names. Use the hosting
Environment tab for passwords, API keys and database paths. Use HTTPS.

**Back up and retain existing `aa_hub.db`, `tx_hub.db`, and `study_time.db`.**
The old host screenshot showed an unrelated CricEdge installation mixed with
Study Hub files. A GitHub merge or automatic pull cannot guarantee those old
host files will be deleted; cutover must be done in the actual hosting Files
manager after verification.

See [Bot-Hosting deployment guide](deployment/BOT_HOSTING_SETUP.md) and
[full requirements](JAY_STUDY_HUB_REBUILD_REQUIREMENTS.md).

## Study-time integrity and limitations

Study time is credited automatically when a Study Hub browser tab is both
visible and window-focused. Clicks/typing are **not** required. Background tabs,
offline/sleep gaps, and simultaneous tabs are handled conservatively. Views of
Self Overview itself do not earn study minutes. Time totals are saved separately
for AA and TX using Kuwait local date/hour boundaries.

Browser focus cannot prove actual attention or prevent intentional forgery by
an authorised user. Authentication protects private pages but is not
identity-grade proof of activity. The first deployment is not considered
complete until private storage persists across hosting restarts.

## Scope

Existing quizzes and notes remain as available in the current project; no
external Jotform or Google Sheets sync is claimed until such integrations are
implemented and verified. A topic is only complete after teaching, testing,
marking, correction, successful retesting where needed, and exam-standard
application.


## Study Board — chapter PDF + editable spreadsheet

Open **Study Board** from the AA/TX sidebar or from any chapter card. Each
subject/chapter has its own private resource library.

- Upload PDF, Markdown/TXT study notes and Excel files.
- Open PDF textbooks in a continuous-scrolling reader with page navigation,
  zoom in/out (buttons, dropdown, Ctrl-scroll), rotate, find and download.
- Create and edit notes or view existing TX chapter notes.
- Work in an Excel-style [Univer Sheets](https://univer.ai) spreadsheet next to
  the PDF. Supports core spreadsheet editing, formulas, standard formatting,
  sheet tabs and zoom. The PDF and spreadsheet share a resizable split view,
  with single-pane and narrow-screen modes.
- Import XLSX/XLS/CSV and export basic XLSX using SheetJS Community Edition.
  This is **not Microsoft Excel**, and it does not claim full VBA, Power Query,
  chart, formatting or formula compatibility. Use the "Excel for web" link
  for the original Microsoft Excel application.
- Workbook snapshots are stored on the server (not only in browser storage),
  with 20-second foreground autosave, manual Save, and revision checking.

**Your PDFs uploaded in ChatGPT are not automatically hosted on Bot-Hosting.**
For licensed study books, sign into the Hub and upload through Study Board.
Do not commit those PDFs to GitHub. The default document upload limit is 32 MB.

### Persistent storage

Set \`BOARD_STORAGE_PATH\` to a persistent writable directory. It contains the
private \`study_board.sqlite3\` workbook catalog and \`documents/\` PDFs/notes,
all excluded from public Git. The backup script includes these files.

In addition to the usual Python backend, Study Board uses pinned public-CDN
versions of PDF.js, Univer, and SheetJS. External CDN access is required.
See \`deployment/BOT_HOSTING_SETUP.md\` and \`deployment/manifest.json\`.

