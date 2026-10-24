# ACCA Financial Reporting (FR / F7) Practice Portal

F7-only hosted practice portal for Jayakiran, built with Python/Flask for Bot-Hosting.

## Features

- Real Google OAuth sign-in on the hosted site.
- Email/username + fallback-password login.
- New Google emails must choose a username and fallback password once.
- Editable profile with name, username, email, password and profile picture.
- FR/F7 dashboard, mock library, analytics, history and retests.
- ACCA-style exam interface with timer, 10-minute warning, scratch pad, calculator, navigator/review flow, Section C workspaces and PDF exports.
- Management page for importing structured mock JSON files.

## URLs

| URL | Purpose |
| --- | --- |
| `/` | FR/F7 portal |
| `/login` | Google or fallback sign-in |
| `/auth/google` | Start Google OAuth |
| `/auth/google/callback` | Google callback |
| `/complete-account` | One-time fallback setup for new Google emails |
| `/api/profile` | Signed-in profile API |
| `/health` | Deployment/OAuth status |

## Bot-Hosting variables

Set these privately on Bot-Hosting:

- `FLASK_SECRET_KEY`
- `F7_DB_PATH` on persistent storage
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI=https://YOUR-HOST-DOMAIN/auth/google/callback`

Do not commit Google secrets to GitHub.

## F7-only cutover

The owner explicitly requested deletion of the previous AA/F8 and TX/F6 site and data. On first startup, the F7 app deletes the old AA/TX/study-time databases and Study Board storage paths, and removes legacy AA/TX source assets that may remain on the host.

The old AA/TX modules, templates, static assets and tests are removed from this repository.

## Run

```bash
python -m pip install -r requirements.txt
python app.py
```

For local HTTP testing only set `HUB_ALLOW_HTTP=1`. Production should use HTTPS.

Account/profile data is server-side in `f7_portal.db`. Mock attempt/history data in the current exam UI is still browser-local storage; server-side cross-device attempt sync can be added later.
