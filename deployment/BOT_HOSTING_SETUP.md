# F7-only Bot-Hosting deployment

This revision replaces the former AA/F8 + TX/F6 Study Hub with ACCA Financial Reporting (FR/F7) only.

## Runtime

- Python 3.11+
- Startup: `python app.py`
- HTTPS required for Google OAuth.

## Private environment variables

```text
FLASK_SECRET_KEY=<long random persistent secret>
F7_DB_PATH=<persistent path>/f7_portal.db
GOOGLE_CLIENT_ID=<Google OAuth Web application client id>
GOOGLE_CLIENT_SECRET=<Google OAuth client secret>
GOOGLE_REDIRECT_URI=https://YOUR-HOST-DOMAIN/auth/google/callback
```

If the Google client ID/secret is missing, the Google button opens a setup page and displays the callback URI instead of faking authentication.

## Google Cloud

1. Configure the OAuth consent screen.
2. Create OAuth credentials of type **Web application**.
3. Add `https://YOUR-HOST-DOMAIN/auth/google/callback` as an authorised redirect URI.
4. Put the client ID and secret in Bot-Hosting private environment variables.
5. Restart/redeploy.
6. Open `/login` and choose **Continue with Google**.
7. For a new Google email, choose a username and fallback password once.

## Legacy deletion

At the owner's explicit request, the first F7-only startup removes previous F8/F6 databases, study-time data, Study Board storage and leftover AA/TX source assets. This is intentionally destructive.
