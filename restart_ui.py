import os
import hmac
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from flask import Blueprint, request, render_template_string

restart_ui = Blueprint("restart_ui", __name__)

PAGE = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="background:#101a2a;color:white;font:16px system-ui;padding:32px"><main style="max-width:480px;margin:40px auto"><a href="/" style="color:skyblue">AA / F8</a> | <a href="/tx/" style="color:skyblue">TX / F6</a><h1>Restart hosting</h1><p>Restarting will briefly disconnect both subjects.</p><p>{{message}}</p>{% if enabled %}<form method="post"><input type="password" name="password" placeholder="Admin password" required style="padding:12px"><button type="submit" style="padding:12px">Restart now</button></form>{% endif %}</main></body></html>"""

@restart_ui.route("/admin/restart", methods=["GET","POST"])
def restart_page():
    key=os.environ.get("BOT_HOSTING_API_KEY")
    deployment=os.environ.get("BOT_HOSTING_DEPLOYMENT_ID")
    password=os.environ.get("SITE_RESTART_PASSWORD")
    enabled=bool(key and deployment and password)
    if request.method=="GET":
        message="Enter the admin password to restart." if enabled else "To enable one-click restart, set BOT_HOSTING_API_KEY, BOT_HOSTING_DEPLOYMENT_ID and SITE_RESTART_PASSWORD as private environment variables on the hosting service."
        return render_template_string(PAGE,message=message,enabled=enabled)
    if not enabled or not hmac.compare_digest(request.form.get("password",""),password):
        return render_template_string(PAGE,message="Not configured or incorrect password.",enabled=enabled),403
    if not deployment.startswith("dep_"):
        return render_template_string(PAGE,message="Deployment ID must start with dep_.",enabled=enabled),400
    url="https://bot-hosting.net/api/v1/deployments/"+deployment+"/power"
    payload=json.dumps({"action":"restart","waitSeconds":1}).encode()
    req=Request(url,data=payload,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
    try:
        with urlopen(req,timeout=15) as response:
            result=json.load(response)
        message="Restart requested. Check hosting logs for successful startup." if result.get("ok") else "Restart request was not accepted."
    except HTTPError as exc:
        hints={400:"Invalid request or deployment ID.",401:"API key rejected.",403:"API key lacks power permission or deployment access.",404:"Deployment not found.",429:"Rate limit reached."}
        message="Bot-Hosting HTTP "+str(exc.code)+": "+hints.get(exc.code,"Check API configuration.")
    except (URLError, TimeoutError):
        message="Connection failed or timed out. Check the hosting console before retrying."
    except (ValueError, OSError):
        message="Unexpected API response. Check hosting console before retrying."
    return render_template_string(PAGE,message=message,enabled=enabled)
