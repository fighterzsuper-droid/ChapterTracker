# Jay Study Hub — Rebuild Requirements (Authoritative Draft)

Last updated: 2026-10-17
Status: CLEAN REBUILD FILES PREPARED AND TESTED IN PR #3 — not deployed; live data backups still required.
Owner: Jayakiran (Jay). This is **Jay's project only**; do not mix it up with his brother's separate project, files, grades or study records.

## Confirmed by Jay — preserve these instructions

### 1. Purpose and hosting
- Completely replace old CricEdge bot files in the Bot-Hosting deployment with a **clean dedicated Jay Study Hub**.
- The hosting manager currently contains a `Files / cogs` directory with a mixture of cricket-related files, study hub files, and databases. Do not equate GitHub repository contents with files already on the server.
- Use an existing Bot-Hosting Python website; the current application has been a Flask app with `app.py` as its entry point. A clean rebuild may change architecture only after discussion.
- Jay no longer needs CricEdge; avoid including CricEdge functionality.
- First **collect and record every requested new feature**, then design/build the replacement. Treat future requests as additions to this document; do not silently discard earlier ones.

### 2. Study subjects and personal data
- The existing Study Hub has ACCA Audit & Assurance (AA/F8) and Taxation (TX/F6) sections.
- Preserve separate AA and TX databases/records and identifiable study progress rather than combining or confusing them.
- Follow the AA project's strict progress workflow: syllabus coverage, Topic Progress, Error Log, Assessment Log and Dashboard. Record marks and detailed technical, formula, interpretation, requirement-reading, and exam-technique weaknesses. Only resolve a weakness after successful retesting.
- After each topic/topic-part: challenging scenario-based MCQs and suitable written questions, preferably via Jotform as specified for the AA project. Mark strictly, correct weaknesses and retest before completion.
- Rebuilding the site must not imply that recorded study progress is reset. Preserve by default; migration or reset requires Jay's decision.
- Jay's existing AA progress tracker and his brother's tracking files must remain separate.

### 3. Focus-only time tracking (strict)
- Count study time automatically when the **Jay Study Hub tab is visible and its browser window is focused**.
- Counting must **not** require clicks, mouse movement, keyboard input or pressing an activity button. Quiet reading in the visible focused tab must count.
- Switching to another browser tab or app, minimising the window, or otherwise hiding/unfocusing the study page must **pause counting**.
- Returning focus to the hub must resume automatically.
- The goal is a conservative measurement of focused-tab time with prevention of background-tab inflation, duplicate-tab double counting, offline/sleep catch-up and manipulated elapsed-time requests wherever technically feasible.
- Transparency: browser focus is not proof of real concentration. Do not claim a browser can independently verify attention.
- Activity on an analytics/status page should not artificially count as learning time unless Jay explicitly changes that rule.

### 4. Self Overview and Kuwait time
- Create a navigable section named **Self Overview** inside Jay Study Hub itself, hosted on Bot-Hosting.
- Jay proposed a `watcher.py` component to provide monitoring and live statistics; it can run as part of the main Flask app, and need not be a second hosting process.
- Show a **live Kuwait local clock** (Asia/Kuwait, UTC+03:00), preferably referenced to authoritative server time, independent of an incorrect device timezone.
- Show today's real-time focused study minutes and broader totals (e.g. seven-day and cumulative).
- Graph actual recorded study time **hour by hour across each Kuwait-local day**, with daily graphs and historical views. Support growing Self Overview with future metrics Jay describes later.
- Support distinction between AA and TX study statistics and optionally combined totals. Preserve the exact local date/hour boundaries.

### 5. Clean deployment and backups
- Jay wants to remove **all files and folders not needed** for Study Hub from the **actual Bot-Hosting Files interface**, not merely the GitHub repository.
- Current hosting screenshot shows CricEdge-related modules and database(s), plus `aa_hub.db`, `tx_hub.db`, `.env`, `app.py`, `tx_hub.py`, `templates/`, `static/`, `requirements.txt`, `restart_ui.py`, etc.
- **Do not delete the production directories yet.** First export/download and verify backups of `aa_hub.db`, `tx_hub.db`, any `study_time.db`, and any additional existing study data. Preserve configuration; treat `.env` as secret and **never copy its values into GitHub**.
- Make and test the replacement from clean source before replacing old server files, confirm the real configured startup directory and entrypoint, then deploy with rollback capability.
- Do not assume a GitHub change deletes pre-existing Bot-Hosting files. The site may reside under `cogs/` within a mixed deployment.
- Do not claim to have altered live Bot-Hosting files unless actual supported hosting access is available.

## Existing work (not necessarily deployed)
- GitHub repository: `fighterzsuper-droid/ChapterTracker`, default branch `main`.
- Open pull request #2: `https://github.com/fighterzsuper-droid/ChapterTracker/pull/2` includes a provisional foreground timer, `study_time.py`, `watcher.py`, Self Overview, and graphs. It is **not** the final rebuild design and should not be presumed deployed.
- Existing Python app currently has AA and TX Flask components, HTML templates, static CSS/JS, and SQLite. Treat this as a reference while creating the clean replacement, not a commitment to keep all modules.

## Safety requirements before any destructive cutover
1. Obtain a full directory listing from the live host and confirm which service/process actually runs there.
2. Create **off-host backups** of user databases and configuration before deletion; ensure backups can be restored.
3. Preserve and migrate existing study records, without conflating Jay's and brother's records.
4. Build and test the clean application separately. Verify navigation, quiz/history persistence, focus timing, Kuwait clock and graphs.
5. Document exactly which directories can be removed. Do not remove or publish secret files.
6. Perform deployment/cutover only after Jay has reviewed the specification and necessary backups are confirmed.

## Awaiting Jay's next requirements / decisions
- Full feature list and desired UI for the rebuilt Study Hub.
- Whether existing AA/TX historical progress is to be imported exactly as-is (default: preserve).
- Which sections should be included in version 1 beyond the already requested features.
- Available hosting backup/persistent storage details.
- Any authentication/privacy preferences (recommended for a secure private dashboard).

## Chapter Study Board — requested 2026-10-17
- Add **Study Board** link in sidebar and from each AA/F8 chapter and TX/F6 topic.
- A private chapter resource library for PDFs, text/Markdown study notes, and workbooks.
- Upload PDFs and notes directly through the signed-in site; never commit the licensed AA study text/exam kit PDFs to public GitHub.
- Full PDF reading UI with scrolling, page navigation, search, zoom in/out, fit width, Ctrl-scroll zoom, rotate, and download.
- Built-in editable chapter notes plus access to the existing TX revision notes.
- Excel-style spreadsheet editor powered by Univer Sheets with formulas, standard editing/formatting, sheet tabs and zoom, chapter-linked server persistence, autosave and explicit Save.
- Import .xlsx/.xls/.csv and export basic .xlsx using SheetJS; **do not claim exact Microsoft Excel parity** (e.g. macros/VBA and advanced features are not fully supported). Offer "Excel for web" to use Microsoft's actual Excel when needed.
- Resizable split view showing PDF/notes and spreadsheet at once, plus single-pane modes, responsive stacked view on mobile.
- Uploaded documents, workbooks and metadata must remain private, excluded from Git and included in off-server backups using a persistent \`BOARD_STORAGE_PATH\`.
- The Study Board must count focused study time under the correct AA/TX subject without counting background browser tabs.
- Status: implementation staged on feature branch. Separate hosting deployment and private-data persistence tests remain necessary before claiming the live website has changed.

## Study Board expansion — 2026-10-19
- An **Expand view** control must make the complete PDF/notes-and-spreadsheet workspace fill the browser viewport while retaining access to the tools.
- Individual **Expand notes** and **Expand sheet** controls must maximize either pane, with a one-click restore to the previous split or single-pane layout.
- **Hide library / Show library** must allow the note and spreadsheet panes to use the width previously taken by the chapter library.
- The split divider must remain draggable/keyboard accessible, support asymmetric widths (15%–85%), and remember the user's chosen width.
- Escape must exit expanded mode and restore the prior layout without clearing unsaved content.
- Ordinary non-expanded Study Board should use more vertical screen height.
- Preserve AA/TX focus timer behavior and note/workbook data without migration or resets.

## Change log
- 2026-10-17: Added new Study Board requirements and implementation scope: PDF reader, chapter notes, editable Univer spreadsheet, XLSX import/export and split view, retaining private storage.
- 2026-10-17: User authorised preparing all clean Study Hub files. Complete project source, password login, persistent AA/TX/time storage, Kuwait Self Overview, deployment manifest, host audit, SQLite backup utility and test suite staged in PR #3. Live Bot-Hosting files and databases untouched.
- 2026-10-17: Initial durable rebuild brief created based on Jay's requests in this chat. No host deletion authorised or executed.
