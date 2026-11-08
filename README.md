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

## Topic Tests (Chapter-Level Exams)

- Sign in and open **Topic Tests** in the left navigation, or visit `/topic-tests`.
- The **Chapter 22 C2.1 Profitability & Efficiency** test has 12 scenario MCQs and two written questions (40 marks).
- MCQs are marked when submitted. Written responses are retained for strict tutor marking; do not treat the objective score alone as a final grade.
- Attempts are stored in the existing persistent `F7_DB_PATH` SQLite database, separately for each signed-in user. Draft answers autosave locally in that user's browser.
- The **Review attempt** page shows MCQ corrections and full saved written answers and allows copying a submission for external marking. Past submitted attempts remain accessible after new tests are published.
- Future tests are **new entries with unique quiz IDs** in `fr_topic_tests.json`; never overwrite a published test with attempts. Revisions and targeted weakness retests use new IDs.
- The GitHub Actions verification checks the question bank, authentication, complete submissions, objective scoring and topic-test JavaScript.
- Bot-Hosting must pull the newest `main` commit (using **Pull now** or restart when **Auto-pull at restart** is enabled) for new tests to appear on the running site.

## GitHub Sync from the Management panel

Admins can open **Management → GitHub deployment updates** to compare the latest
`main` commit against the running Git checkout and select **Pull latest commits & restart**.
The button invokes Bot-Hosting's official `POST /api/v1/deployments/:id/sync` service,
which pulls the linked repository and restarts the live Python app.

**One-time setup:**

1. In Bot-Hosting, open **Account → Developer** and create an API key with the
   `deployments:write` and `deployments:read` scopes. The read scope allows
   the site to diagnose a 404 and identify the correct F7 deployment. No
   GitHub personal access token is needed.
2. Save it as the **private** Bot-Hosting environment variable `BOT_HOSTING_API_KEY`.
   Never place it in GitHub, website JavaScript, or a chat message.
3. The default deployment ID is the existing F7 website deployment. If moved or
   recreated, set `BOT_HOSTING_DEPLOYMENT_ID` privately to its new deployment ID.
4. Use Bot-Hosting **GitHub → Pull now** or restart once to deploy this feature.
   Thereafter the website's Management button can request future pulls.

If **Pull latest commits** displays a 404, the API key may not be authorised
for this deployment even when the Bot-Hosting dashboard can see it. Confirm the
key belongs to the deployment owner or an account granted access, and that it
has both read/write deployment scopes. The website now verifies any recovered
ID against BOTH the known F7 public URL and linked GitHub repo before retrying.
You can always use the Bot-Hosting dashboard's **GitHub → Pull now** as a fallback.

The admin API requires the signed-in administrator account and a CSRF token.
It never accepts a repository, branch or arbitrary command from the client.
Pulls can interrupt in-progress tests; save work before confirming.
Do not mark a deployment as updated until Bot-Hosting confirms the operation.
The persistent `F7_DB_PATH` database is not altered by this feature.

## Navigation and exam safety

- The Topic Tests area has the same section links as the main portal, a
  14-question navigator, skip/previous/next, flag-for-review and keyboard
  left/right navigation (outside text inputs).
- **Save & Exit to Home** and **Save & Back to Tests** keep local drafts without
  recording a grade. Only explicit confirmed submissions create attempts.
- Mock Exams also have a **Save & Exit to Home** control and a confirmation
  warning before the explicit scoring action, so visiting Question 32
  cannot silently create a zero-mark attempt.
- Dashboard metric cards and headings have direct arrows to the relevant
  History, Analytics, Retests, Mocks, Topic Tests, and Progress areas.

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
