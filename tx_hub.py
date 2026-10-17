import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from html import escape
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
("13","Mixed income tax consolidation"),
("14","Capital gains tax: disposals and reliefs"),
("15","Inheritance tax: lifetime transfers and death estates"),
("16","Corporation tax: profits, losses and groups"),
("17","VAT: registration, computations and administration"),
("18","Integrated TX mock examinations")
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
        CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, topic TEXT, due TEXT, done INTEGER NOT NULL DEFAULT 0);
        """)
        for code,name in TOPICS:
            c.execute("INSERT OR IGNORE INTO topics(code,title,notes_created,status) VALUES(?,?,?,?)",(code,name,1 if code in ('1A','1B','1C','1D','1E') else 0,"Notes available" if code in ('1A','1B','1C','1D','1E') else "Not Started"))
initialize()
def page(title, content):
    shell = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} — Jay's Exam Hub</title><link rel="stylesheet" href="/static/style.css"></head><body>
    <div class="shell"><aside class="sidebar"><div class="brand"><div class="brand-mark">TX</div><div><strong>Jay's Exam Hub</strong><span>ACCA Taxation • TX / F6</span></div></div>
    <nav><a class="{{ 'active' if path == '/tx/' else '' }}" href="/tx/">Dashboard</a><a class="{{ 'active' if path == '/tx/topics' else '' }}" href="/tx/topics">Chapters</a><a class="{{ 'active' if path == '/tx/quiz' else '' }}" href="/tx/quiz">Tests</a><a class="{{ 'active' if path == '/tx/weaknesses' else '' }}" href="/tx/weaknesses">Weaknesses</a><a class="{{ 'active' if path == '/tx/history' else '' }}" href="/tx/history">Assessment History</a><a href="/tx/goals">Goals & To-do</a></nav><div class="sidebar-foot">Jaykiran • TX/F6<br>Progress is not complete until retested and applied.</div></aside>
    <main><header class="topbar"><div><h1>{{ title }}</h1><p>Exam-focused study, testing and weakness tracking.</p></div>
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-left:auto"><label for="subject-switch" style="font-size:13px">Subject</label><select id="subject-switch" onchange="location.href=this.value" style="padding:10px 14px;border-radius:10px;border:1px solid #58708c;background:#1b2a40;color:white"><option value="/">AA / F8</option><option value="/tx/" selected>TX / F6</option></select><a href="/admin/restart" class="button ghost">Restart hosting</a></div></header>
    {{ content|safe }}</main></div><script src="/static/study_time.js" defer></script></body></html>"""
    return render_template_string(shell, title=title, content=content, path=request.path)
@tx.get("/")
def home():
    with connect() as db:
        rows=db.execute("SELECT * FROM topics ORDER BY rowid").fetchall()
        attempts=db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 5").fetchall()
        weak=db.execute("SELECT COUNT(*) FROM weaknesses WHERE status LIKE 'Open%'").fetchone()[0]
        goals=db.execute("SELECT * FROM goals WHERE done=0 ORDER BY due IS NULL,due,id LIMIT 5").fetchall()
    notes=sum(int(x["notes_created"]) for x in rows)
    completed=sum(x["status"]=="Complete" for x in rows)
    avg=round(sum(x["score"]/x["max_marks"]*100 for x in attempts)/len(attempts),1) if attempts else None
    cards=[("Notes available",str(notes)+" / "+str(len(rows)),"Revision notes, not completed chapters"),("Officially complete",str(completed),"Only after exam-standard progression"),("Open weaknesses",str(weak),"Awaiting correction and successful retest"),("Average mark",str(avg)+"%" if avg is not None else "—","Recent recorded TX attempts")]
    kpis='<div class="kpi-grid">'+''.join('<div class="card kpi"><span>'+a+'</span><strong>'+b+'</strong><small>'+d+'</small></div>' for a,b,d in cards)+'</div>'
    progress=''.join('<div><b>'+escape(r["code"])+'</b><span>'+escape(r["title"])+'</span><em class="'+("inprogress" if r["status"]!="Not Started" else "neutral")+'">'+escape(r["status"])+'</em></div>' for r in rows[:9])
    tasks=''.join('<p class="muted">'+escape(g["title"])+('</p>') for g in goals) or '<p class="muted">No active goals yet.</p>'
    recent=''.join('<tr><td>'+escape(r["topic"])+'</td><td>'+str(r["score"])+'/'+str(r["max_marks"])+'</td><td>'+escape(r["submitted_at"][:10])+'</td></tr>' for r in attempts) or '<tr><td colspan="3">No attempts yet.</td></tr>'
    content=kpis+'<div class="two-col"><section class="card"><div class="card-head"><div><span class="eyebrow">SYLLABUS</span><h2>Topic progress</h2></div><a class="text-link" href="/tx/topics">View all</a></div><div class="progressbar"><span style="width:'+str(round(notes/len(rows)*100,1))+'%"></span></div><p class="muted">'+str(notes)+' parts have revision notes. Notes do not equal completion.</p><div class="chapter-mini">'+progress+'</div></section><section class="card"><span class="eyebrow">STUDY PLANNER</span><h2>Goals & to-do</h2>'+tasks+'<a class="button" href="/tx/goals">Manage goals</a><a class="button ghost" href="/tx/quiz">Take diagnostic</a></section></div><div class="two-col"><section class="card"><span class="eyebrow">CURRENT FOCUS</span><h2>Income tax 1A–1E</h2><p class="muted">Open detailed revision notes and worked examples. Assessment and successful retesting are required before marking a topic complete.</p><a class="button" href="/tx/notes/1A">Open study notes</a></section><section class="card"><span class="eyebrow">EXAM TECHNIQUE</span><h2>Correct and retest</h2><p class="muted">All technical and interpretation weaknesses remain open until demonstrated correct in a later assessment.</p><a class="button ghost" href="/tx/weaknesses">Weakness log</a></section></div><section class="card"><div class="card-head"><div><span class="eyebrow">RECENT</span><h2>Assessment history</h2></div><a class="text-link" href="/tx/history">Full history</a></div><div class="table-wrap"><table><thead><tr><th>Topic</th><th>Score</th><th>Date (UTC)</th></tr></thead><tbody>'+recent+'</tbody></table></div></section>'
    return page("Dashboard",content)

@tx.get("/topics")
def topics():
    with connect() as db: rows=db.execute("SELECT * FROM topics ORDER BY rowid").fetchall()
    cards=[]
    for r in rows:
        steps=''.join('<span class="'+("done" if r[k] else "")+'">'+label+'</span>' for k,label in [("taught","Taught"),("tested","Tested"),("marked","Marked"),("corrected","Corrected"),("retested","Retested"),("applied","Applied")])
        notes='<a class="button ghost" href="/tx/notes/'+escape(r["code"])+'">Study notes</a>' if r["code"] in ("1A","1B","1C","1D","1E") else ""
        cards.append('<article class="card chapter-card"><span class="eyebrow">PART '+escape(r["code"])+'</span><h2>'+escape(r["title"])+'</h2><div class="chips"><span class="chip '+("yes" if r["notes_created"] else "no")+'">'+("Notes available" if r["notes_created"] else "Notes not created")+'</span><span class="chip '+("progress" if r["status"]!="Not Started" else "no")+'">'+escape(r["status"])+'</span></div><div class="steps">'+steps+'</div>'+notes+'</article>')
    return page("TX Syllabus & Topic Progress",'<div class="info-box">FA2025 teaching roadmap, not Kaplan chapter numbering. Includes income tax, CGT, IHT, corporation tax and VAT. Notes available is not topic completion.</div><div class="chapter-grid">'+''.join(cards)+'</div>')

@tx.route("/goals",methods=["GET","POST"])
def goals():
    if request.method=="POST":
        action=request.form.get("action","add")
        with connect() as db:
            if action=="add":
                title=request.form.get("title","").strip()[:180]
                due=request.form.get("due","").strip()
                if title: db.execute("INSERT INTO goals(title,due) VALUES(?,?)",(title,due or None))
            elif action in ("toggle","delete"):
                try: gid=int(request.form.get("id","0"))
                except ValueError: gid=0
                if action=="toggle": db.execute("UPDATE goals SET done=1-done WHERE id=?",(gid,))
                else: db.execute("DELETE FROM goals WHERE id=?",(gid,))
        return redirect(url_for("tx.goals"))
    with connect() as db: rows=db.execute("SELECT * FROM goals ORDER BY done,due IS NULL,due,id DESC").fetchall()
    form='<section class="card"><span class="eyebrow">STUDY PLANNER</span><h2>Add a goal or to-do</h2><form method="post" class="tx-goal-form"><input name="title" maxlength="180" required placeholder="e.g. Complete five income tax computations"><input name="due" type="date"><button class="button" type="submit">Add goal</button></form></section>'
    items=[]
    for r in rows:
        actions=''
        for action,label in [("toggle","Reopen" if r["done"] else "Mark done"),("delete","Delete")]:
            actions+='<form method="post"><input type="hidden" name="action" value="'+action+'"><input type="hidden" name="id" value="'+str(r["id"])+'"><button class="button ghost" type="submit">'+label+'</button></form>'
        items.append('<article class="card tx-task"><div><span class="eyebrow">'+("COMPLETED" if r["done"] else "TO DO")+'</span><h2>'+escape(r["title"])+'</h2><p class="muted">'+("Due "+escape(r["due"]) if r["due"] else "No deadline")+'</p></div><div class="tx-task-actions">'+actions+'</div></article>')
    done=sum(int(r["done"]) for r in rows)
    stats='<div class="kpi-grid">'+''.join('<div class="card kpi"><span>'+label+'</span><strong>'+str(val)+'</strong></div>' for label,val in [("Total goals",len(rows)),("Completed",done),("Remaining",len(rows)-done),("Completion rate",str(round(done/len(rows)*100) if rows else 0)+"%")])+'</div>'
    return page("Goals & To-do",stats+form+'<div class="tx-task-list">'+(''.join(items) if items else '<div class="empty">No goals yet.</div>')+'</div><div class="info-box">Completing a to-do does not mark a topic complete. Exam-standard assessment and retesting are still required.</div>')


STUDY_NOTES={
"1A":[("Classifying income","Non-savings income includes employment, trading and property income; savings includes bank interest; dividends are a separate category. The usual tax order is non-savings, savings, then dividends."),("Income tax computation","Calculate total income, deduct qualifying reliefs to obtain net income, then the available personal allowance to obtain taxable income. Tax each income category using its applicable bands."),("Worked example","Employment £38,000, property £5,000, bank interest £1,200 and dividends £2,000 give non-savings £43,000, savings £1,200, dividends £2,000 and total income £46,200. Assuming full personal allowance £12,570 and no reliefs, taxable income is £33,630."),("Exam technique","Present separate income categories and clear subtotals. Do not confuse total income with taxable income.")],
"1B":[("Personal allowance","The standard personal allowance for 2025/26 is £12,570. It falls by £1 for each £2 of adjusted net income above £100,000 and is nil at £125,140."),("Adjusted net income","Grossed-up qualifying Gift Aid and relief-at-source pension contributions can reduce adjusted net income."),("Worked example","Adjusted net income £110,000: excess £10,000; allowance reduction £5,000; remaining allowance £7,570."),("Exam trap","Reduce the allowance by half the excess over £100,000, not by the whole excess.")],
"1C":[("Non-savings rates","For England, Wales and Northern Ireland in 2025/26, taxable non-savings income is generally charged at 20% on the first £37,700, 40% at higher rate and 45% at additional rate. Scottish non-savings rates differ."),("Worked example","Taxable non-savings income £50,000: £37,700 × 20% = £7,540; £12,300 × 40% = £4,920; total £12,460."),("Exam trap","Tax bands apply to taxable income. Gross Gift Aid and relief-at-source pension contributions can extend rate bands.")],
"1D":[("Starting rate for savings","Up to £5,000 of savings income can qualify for the 0% starting rate, reduced pound for pound by taxable non-savings income."),("Savings nil-rate band","Normally £1,000 for basic-rate, £500 for higher-rate and nil for additional-rate taxpayers. Savings taxed at 0% still occupy tax-band capacity."),("Worked example","With taxable non-savings income £3,000, £2,000 of the savings starting-rate band remains. Apply that to qualifying savings before considering the savings nil-rate band."),("Exam trap","Nil-rate savings still count toward total taxable income and band usage.")],
"1E":[("Dividend income","The 2025/26 dividend nil-rate band is £500. Dividends are the top slice after non-savings and savings income."),("Dividend tax rates","The 2025/26 rates are 8.75% basic, 33.75% higher and 39.35% additional. The £500 nil-rate band still uses tax-band capacity."),("Worked example","With taxable non-savings income £35,000 and dividends £4,000, £2,700 of dividends falls in the basic band. £500 at 0%, £2,200 at 8.75% (£192.50) and £1,300 at 33.75% (£438.75). Dividend tax £631.25."),("Exam technique","Compute non-savings, savings and dividend slices in order. Show the nil-rate band explicitly.")]
}

@tx.get("/notes/<code>")
def notes(code):
    if code not in STUDY_NOTES: abort(404)
    nav=''.join('<a class="button ghost" href="/tx/notes/'+k+'">Part '+k+'</a>' for k in STUDY_NOTES)
    blocks=''.join('<section class="card tx-note"><span class="eyebrow">REVISION NOTES</span><h2>'+escape(h)+'</h2><p>'+escape(v)+'</p></section>' for h,v in STUDY_NOTES[code])
    return page("Income Tax "+code,'<div class="info-box">TX-UK Finance Act 2025 / 2025–26. These are revision summaries and examples, not complete Kaplan chapters. Full exam-standard practice and successful retesting are required.</div><div class="tx-note-nav">'+nav+'</div>'+blocks+'<section class="card"><h2>Next actions</h2><a class="button" href="/tx/quiz">Foundation diagnostic</a><a class="button ghost" href="/tx/goals">Add practice goal</a></section>')

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
        return page("TX 1A Diagnostic Result",'<div class="card"><h2>Score: '+str(score)+'/8</h2><p>Incorrect responses are logged as open weaknesses. A later successful retest is required before resolving them. This diagnostic alone does not complete the topic.</p><a href="/tx/quiz">Try again</a> · <a href="/tx/weaknesses">Review weaknesses</a></div>')
    parts=[]
    for i,(prompt,opts,_,_) in enumerate(QUESTIONS):
        parts.append('<div class="card question"><h3>Question '+str(i+1)+' (2 marks)</h3><p>'+prompt+'</p>'+''.join('<label><input type="radio" name="q'+str(i)+'" value="'+str(j)+'" required> '+opt+'</label>' for j,opt in enumerate(opts))+'</div>')
    return page("TX Part 1A — Diagnostic Quiz",'<p>Four short foundation questions. More demanding scenario-based assessments will follow.</p><form method="post">'+''.join(parts)+'<button type="submit">Submit answers</button></form>')
@tx.get("/history")
def history():
    with connect() as c: rows=c.execute("SELECT * FROM attempts ORDER BY id DESC").fetchall()
    return page("TX Assessment History",'<div class="card">'+(''.join('<p>Part '+r['topic']+' — '+str(r['score'])+'/'+str(r['max_marks'])+' — '+r['submitted_at']+'</p>' for r in rows) or 'No TX assessments submitted yet.')+'</div>')
@tx.get("/weaknesses")
def weaknesses():
    with connect() as c: rows=c.execute("SELECT * FROM weaknesses ORDER BY id DESC").fetchall()
    return page("TX Weakness Log",'<div class="card">'+(''.join('<p><b>'+r['topic']+' — '+r['category']+'</b><br>'+r['details']+'<br>'+r['status']+'</p>' for r in rows) or 'No TX weaknesses logged yet.')+'</div>')
