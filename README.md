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
