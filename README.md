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
