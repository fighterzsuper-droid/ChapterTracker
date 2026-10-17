# Jay's ACCA AA Exam Hub

Permanent study and assessment portal for Jayakiran's ACCA Audit & Assurance (AA/F8) preparation.

## Bot-Hosting setup

- Connect this repository to the Python deployment.
- Use branch `main`.
- Keep automatic pull on restart enabled.
- Set the startup entry file to `app.py`.
- Restart the deployment.
- Activate the free HTTPS domain from the Domains tab.

The Flask app listens on `0.0.0.0` and uses Bot-Hosting's `SERVER_PORT` automatically.

Assessment attempts and progress are stored in `aa_hub.db`, which is excluded from Git so normal pulls do not replace saved answers.

A chapter is only complete after teaching or review, testing, marking, correction, any required retest, and exam-standard application.


## Automatic foreground study timer

The AA and TX pages show a live **Focused study clock**. Time is credited
automatically when a study-hub tab is visible **and** its browser window is
focused; reading without clicks/keystrokes is counted. Switching tabs,
minimising the window, or focusing a different app pauses the clock.

The browser sends status heartbeats approximately every 10 seconds. The Flask
server, not browser-supplied elapsed seconds, computes and stores credited time.
Gaps longer than 16 seconds earn **no** catch-up time (for example, if the device
sleeps or the network disconnects). A single active lease prevents simultaneous
tabs/devices counting the same wall-clock time twice. Totals are separate for AA
and TX, with a Kuwait-local "today", seven-day rolling total, and all-time total.

Data is kept in study_time.db in the application directory and excluded
from Git. **Verify the hosting volume survives restarts/redeployments and back
up this file**: the ignore rules by themselves do not make hosting persistent.

This records *foreground-tab time*, not proof of attentive study. The website
does not currently implement user authentication, so these timers are **not
tamper-proof** against someone making their own API requests. A personal login
and persistent remote database would be required before treating the timer as
a secure, independently verifiable record.

Run regression tests with: python -m unittest discover -s tests -v


## Self Overview on the existing Bot-Hosting website

The existing Flask application registers a `watcher.py` Blueprint. **Do not
run watcher.py as a separate bot process**: the normal `app.py` startup
already serves it at `/self-overview`. The navigation sidebar links to it
from both AA/F8 and TX/F6.

Self Overview includes:
- A live clock calibrated from the server and displayed using `Asia/Kuwait`.
- Focused study time today, in the past seven days, and all time.
- A selectable historical day with 24 hourly bars (00:00–23:59 Kuwait).
- Daily activity for the past seven days, plus AA/TX subject filters.
- Automatic chart refresh approximately every ten seconds while visible.

The overview page itself does **not** earn study time. Historical totals
come from the server's `study_day` and `study_hour` SQLite tables; individual
heartbeat intervals are split across local hour and midnight boundaries.

On Bot-Hosting, optionally set `STUDY_TIME_DB_PATH` to an **absolute location
on persistent storage**, for example a path on a hosting volume you know
survives deployment. If unset, it defaults to `study_time.db` next to
`app.py`. Do not rely solely on Git's ignore rules for database durability.
Back up the study database regularly.

The existing application has no login, meaning anyone who can access the
site can currently view the metrics/API and spoof timer requests. Add
server-side authentication before considering the site confidential or
tamper-proof.

After merging the feature branch into `main`, restart the Python deployment
on Bot-Hosting with automatic Git pull enabled. Check `/self-overview`
and confirm that switching away from study pages immediately pauses credit.
