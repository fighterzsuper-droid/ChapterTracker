import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from flask import Blueprint, render_template_string, request, redirect, url_for, flash, abort

tx = Blueprint("tx", __name__, url_prefix="/tx")
DB = Path(__file__).resolve().parent / "tx_hub.db"
TOPICS = [
("1A","Income tax computation and classification"),
("1B","Personal Allowance and adjusted net income"),
("1C","Non-savings income tax bands"),
("1D","Savings income: starting and nil-rate bands"),
("1E","Dividend income and combined computations"),
("1F","Income tax reliefs"),
("1G","Gift Aid donations"),
("1H","Personal pension contributions"),
("1I","Advanced income tax computations"),
("2","Residence and the UK tax system"),
("3","Employment income and taxable benefits"),
("4","Property income"),
("5","Trading income and badges of trade"),
("6","Adjusted trading profits and cash basis"),
("7","Capital allowances"),
("8","Trading losses"),
("9","Partnerships"),
("10","Pensions: detailed rules"),
("11","National Insurance contributions"),
("12","Income tax administration"),
("13","Mixed exam-standard consolidation")
]
def connect():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    return c
def initialize():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS topics (code TEXT PRIMARY KEY, title TEXT NOT NULL, notes_created INTEGER NOT NULL DEFAULT 0, taught INTEGER NOT NULL DEFAULT 0, tested INTEGER NOT NULL DEFAULT 0, marked INTEGER NOT NULL DEFAULT 0, corrected INTEGER NOT NULL DEFAULT 0, retested INTEGER NOT NULL DEFAULT 0, applied INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Not Started', latest_mark REAL);
        CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, submitted_at TEXT NOT NULL, score REAL NOT NULL, max_marks REAL NOT NULL, answers TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS weaknesses (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, category TEXT NOT NULL, details TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open - awaiting retest');
        """)
        for code,name in TOPICS:
            c.execute("INSERT OR IGNORE INTO topics(code,title,notes_created,status) VALUES(?,?,?,?)",(code,name,1 if code in ('1A','1B','1C','1D','1E') else 0,"Notes available" if code in ('1A','1B','1C','1D','1E') else "Not Started"))
initialize()
STYLE="""<style>.txwrap{max-width:1060px;margin:auto;padding:24px;font:16px system-ui;color:#e9eff8;background:#101a2a;min-height:100vh}.txwrap a{color:#8dd8ff}.txwrap .panel{padding:20px;margin:14px 0;background:#1b2a40;border:1px solid #34445a;border-radius:12px}.txwrap table{width:100%;border-collapse:collapse}.txwrap td,.txwrap th{padding:12px;border-bottom:1px solid #3b4b60;text-align:left}.txwrap nav a{margin-right:18px}.txwrap button{background:#7ad0ff;border:0;padding:12px 20px;border-radius:9px;cursor:pointer}.txwrap label{display:block;margin:12px 0}</style>"""
def page(title,content):
    return render_template_string('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }}</title></head><body style="margin:0;background:#101a2a">'+STYLE+'<div class="txwrap"><nav><a href="/">AA / F8</a><a href="/tx/">TX / F6</a><a href="/tx/topics">TX Topics</a><a href="/tx/quiz">TX Quiz</a><a href="/tx/history">TX History</a><a href="/tx/weaknesses">TX Weaknesses</a></nav><h1>{{title}}</h1>'+content+'</div></body></html>',title=title)
@tx.get("/")
def home():
    with connect() as c:
        rows=c.execute("SELECT * FROM topics").fetchall()
        attempts=c.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        weaknesses=c.execute("SELECT COUNT(*) FROM weaknesses WHERE status LIKE 'Open%'").fetchone()[0]
    return page("ACCA TX / F6 — Jaykiran",'<div class="panel"><h2>Taxation (TX-UK), FA2025</h2><p>Separate from AA. Notes for Parts 1A–1E are available; none is marked complete until tested, corrected and successfully retested where necessary.</p><p>Topics: '+str(len(rows))+' | Submitted TX attempts: '+str(attempts)+' | Open TX weaknesses: '+str(weaknesses)+'</p><p><a href="/tx/topics">View full TX syllabus roadmap</a> · <a href="/tx/quiz">Take the 1A diagnostic</a></p></div>')
@tx.get("/topics")
def topics():
    with connect() as c: rows=c.execute("SELECT * FROM topics").fetchall()
    trs=''.join('<tr><td>'+r['code']+'</td><td>'+r['title']+'</td><td>'+r['status']+'</td></tr>' for r in rows)
    return page("TX Topic Progress",'<div class="panel"><p>Notes available is not equivalent to topic completion.</p><table><tr><th>Part</th><th>Topic</th><th>Status</th></tr>'+trs+'</table></div>')
QUESTIONS=[
("Employment £30,000, property £4,000, bank interest £2,000 and dividends £1,000. What is non-savings income?",["£30,000","£34,000","£36,000","£37,000"],1,"income classification"),
("A taxpayer receives £25,000 employment income, £1,500 bank interest and £500 dividends. What is total income?",["£25,000","£26,500","£27,000","£27,500"],2,"total income"),
("Which order is used when taxing these income categories?",["Dividends, savings, non-savings","Savings, dividends, non-savings","Non-savings, savings, dividends","Non-savings, dividends, savings"],2,"tax order"),
("A taxpayer has net income of £40,000 and full Personal Allowance £12,570. What is taxable income?",["£40,000","£27,430","£52,570","£12,570"],1,"taxable income")
]
@tx.route("/quiz",methods=["GET","POST"])
def quiz():
    if request.method=="POST":
        picks=[request.form.get('q'+str(i),'') for i in range(len(QUESTIONS))]
        score=sum(2 for i,p in enumerate(picks) if p==str(QUESTIONS[i][2]))
        import json
        with connect() as c:
            c.execute("INSERT INTO attempts(topic,submitted_at,score,max_marks,answers) VALUES(?,?,?,?,?)",("1A",datetime.now(timezone.utc).isoformat(),score,8,json.dumps(picks)))
            c.execute("UPDATE topics SET tested=1,marked=1,latest_mark=?,status='In Progress' WHERE code='1A'",(score/8*100,))
            for i,p in enumerate(picks):
                if p!=str(QUESTIONS[i][2]):
                    c.execute("INSERT INTO weaknesses(topic,category,details) VALUES(?,?,?)",("1A","Technical / interpretation",QUESTIONS[i][3]+": "+QUESTIONS[i][0]))
        return page("TX 1A Diagnostic Result",'<div class="panel"><h2>Score: '+str(score)+'/8</h2><p>Incorrect responses are logged as open weaknesses. A later successful retest is required before resolving them. This diagnostic alone does not complete the topic.</p><a href="/tx/quiz">Try again</a> · <a href="/tx/weaknesses">Review weaknesses</a></div>')
    parts=[]
    for i,(prompt,opts,_,_) in enumerate(QUESTIONS):
        parts.append('<div class="panel"><h3>Question '+str(i+1)+' (2 marks)</h3><p>'+prompt+'</p>'+''.join('<label><input type="radio" name="q'+str(i)+'" value="'+str(j)+'" required> '+opt+'</label>' for j,opt in enumerate(opts))+'</div>')
    return page("TX Part 1A — Diagnostic Quiz",'<p>Four short foundation questions. More demanding scenario-based assessments will follow.</p><form method="post">'+''.join(parts)+'<button type="submit">Submit answers</button></form>')
@tx.get("/history")
def history():
    with connect() as c: rows=c.execute("SELECT * FROM attempts ORDER BY id DESC").fetchall()
    return page("TX Assessment History",'<div class="panel">'+(''.join('<p>Part '+r['topic']+' — '+str(r['score'])+'/'+str(r['max_marks'])+' — '+r['submitted_at']+'</p>' for r in rows) or 'No TX assessments submitted yet.')+'</div>')
@tx.get("/weaknesses")
def weaknesses():
    with connect() as c: rows=c.execute("SELECT * FROM weaknesses ORDER BY id DESC").fetchall()
    return page("TX Weakness Log",'<div class="panel">'+(''.join('<p><b>'+r['topic']+' — '+r['category']+'</b><br>'+r['details']+'<br>'+r['status']+'</p>' for r in rows) or 'No TX weaknesses logged yet.')+'</div>')
