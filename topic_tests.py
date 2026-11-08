"""Authenticated ACCA FR topic tests, backed by the existing F7 database.

Questions live in fr_topic_tests.json. New versions should be appended with a
new ID; never overwrite a version with submitted attempts.
"""
import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import abort, jsonify, redirect, render_template_string, request, session, url_for

QUESTION_PATH = Path(__file__).resolve().parent / "fr_topic_tests.json"

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ACCA FR | Topic Tests</title>
<style>
:root{font-family:Inter,Arial,sans-serif;color:#17344c;background:#eef4f8}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1120px;margin:auto;padding:22px}
header{background:#103a5c;color:white;padding:15px 22px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header a{color:#d5edff;text-decoration:none}header strong{font-size:19px}header .push{margin-left:auto}
h1{font-size:25px;margin:4px 0 8px}h2{font-size:19px}p{line-height:1.55}
.card{border:1px solid #d5e1ea;background:white;border-radius:12px;padding:20px;margin:15px 0;box-shadow:0 5px 16px #244b6610}
.muted{color:#647f93;font-size:13px}.pill{font-size:12px;background:#e9f3fa;color:#235e82;padding:6px 10px;border-radius:40px;display:inline-block;margin-right:6px}
button,.btn{background:#0c6eab;color:white;border:0;border-radius:8px;padding:11px 17px;cursor:pointer;font-size:14px;font-weight:700}
button:hover{background:#095884}button:disabled{background:#a2b1bd;cursor:not-allowed}
button.secondary{background:#e8f1f7;color:#16476a}button.secondary:hover{background:#d5e7f3}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:12px}
.opt{display:flex;gap:11px;padding:12px;border:1px solid #cad7df;border-radius:8px;margin:9px 0;cursor:pointer;align-items:flex-start}
.opt:hover{background:#f3f9fd}.opt:has(input:checked){background:#e3f3ff;border-color:#0874b6}
.opt input{accent-color:#0b71b0;margin-top:3px}textarea{width:100%;min-height:220px;border:1px solid #bed1dd;border-radius:8px;padding:12px;font:inherit;line-height:1.5}
.question h3{font-size:16px;line-height:1.5;margin-top:0;white-space:pre-wrap}
.question p{white-space:pre-wrap}.toolbar{position:sticky;top:0;z-index:2;background:#f4f8fb;border:1px solid #d4e2ec;border-radius:9px;padding:12px;display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.small{font-size:12px}.hidden{display:none!important}.status{margin:14px 0;padding:12px;border-radius:8px;background:#eef5fa;border:1px solid #d3e4ef}
.result{font-size:24px;font-weight:900}.pre{white-space:pre-wrap;background:#f5f8fa;border:1px solid #dbe6ec;border-radius:8px;padding:13px;font-size:13px;line-height:1.5}
.actions{display:flex;gap:9px;flex-wrap:wrap;margin:16px 0}
.error{color:#a52920}.good{color:#11744b}.toplink{margin-bottom:12px;display:inline-block}
@media(max-width:600px){.wrap{padding:12px}.card{padding:15px}header{padding:13px}.toolbar{position:static}}
</style></head><body data-csrf="{{ csrf }}">
<header><strong>ACCA FR / F7</strong><span>Topic Tests</span><span class="push"></span><a href="/">Dashboard</a></header>
<main class="wrap"><section id="intro"><h1>Chapter practice tests</h1>
<p class="muted">Complete all objective and written answers on this site. MCQs are marked on submission; written answers are saved for strict tutor marking. Past attempts remain accessible.</p>
<div id="catalog" class="grid"></div>
<h2>Your previous submissions</h2><div id="history"></div></section>
<section id="exam" class="hidden"><div class="toolbar"><button class="secondary" id="exit">Back to tests</button><div><b id="examTitle"></b><span class="pill" id="timer">50:00</span></div><span id="answered" class="muted"></span></div>
<div class="card"><p class="muted">40 marks · 12 MCQs (2 marks each) + 2 constructed responses (8 marks each). Recommended closed-book timing. Answers autosave in this browser until submitted.</p></div>
<div id="questions"></div>
<div class="card"><label><input type="checkbox" id="confirm"> I have reviewed my answers and am ready to submit this attempt.</label>
<div class="actions"><button id="submit">Submit all answers</button></div><div id="validation" class="error" role="alert"></div></div>
</section>
<section id="review" class="hidden"><button class="secondary" id="backHistory">Back to Topic Tests</button><div class="card" id="reviewContent"></div></section>
</main>
<script>
(function(){
'use strict';
const csrf=document.body.dataset.csrf;
const intro=document.getElementById('intro'),exam=document.getElementById('exam'),review=document.getElementById('review');
let active=null,startTime=null,ticker=null,userKey=null,reviewRecord=null;
const el=(tag,cls,txt)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(txt!==undefined)x.textContent=txt;return x;};
const show=(which)=>{intro.classList.toggle('hidden',which!=='intro');exam.classList.toggle('hidden',which!=='exam');review.classList.toggle('hidden',which!=='review');window.scrollTo(0,0)};
const niceDate=(s)=>{try{return new Date(s).toLocaleString()}catch(e){return s}};
async function api(path,opts){const res=await fetch(path,Object.assign({credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}},opts||{}));const body=await res.json();if(!res.ok)throw new Error(body.error||'Request failed');return body}
const draftKey=()=> 'fr-topic-draft:'+userKey+':'+active.id;
const timeKey=()=> 'fr-topic-start:'+userKey+':'+active.id;
function saveDraft(){if(!active)return;const answers={};active.questions.forEach(q=>{if(q.type==='mcq'){const x=document.querySelector('input[name="'+q.id+'"]:checked');if(x)answers[q.id]=Number(x.value)}else{const t=document.getElementById('ans-'+q.id);answers[q.id]=t?t.value:''}});localStorage.setItem(draftKey(),JSON.stringify(answers));updateAnswered()}
function readDraft(){try{return JSON.parse(localStorage.getItem(draftKey())||'{}')}catch(e){return {}}}
function updateAnswered(){if(!active)return;let n=0;active.questions.forEach(q=>{if(q.type==='mcq'){if(document.querySelector('input[name="'+q.id+'"]:checked'))n++}else{const t=document.getElementById('ans-'+q.id);if(t&&t.value.trim())n++}});document.getElementById('answered').textContent=n+'/'+active.questions.length+' answered'}
function startTimer(){if(ticker)clearInterval(ticker);let saved=localStorage.getItem(timeKey());if(!saved||!Number(saved)){saved=String(Date.now());localStorage.setItem(timeKey(),saved)}startTime=Number(saved);const update=()=>{const seconds=Math.max(0,(active.duration_minutes||50)*60-Math.floor((Date.now()-startTime)/1000));document.getElementById('timer').textContent=(seconds<=0?'Time elapsed · ':'')+String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');};update();ticker=setInterval(update,1000)}
async function openQuiz(id){
  const data=await api('/api/topic-tests/'+encodeURIComponent(id));active=data.quiz;userKey=data.user_key;
  document.getElementById('examTitle').textContent=active.title;
  const container=document.getElementById('questions');container.replaceChildren();
  const saved=readDraft();
  active.questions.forEach((q,index)=>{
    const card=el('section','card question');
    const hdr=el('h3','',String(index+1)+'. '+q.prompt);card.appendChild(hdr);
    card.appendChild(el('span','pill',q.marks+' marks'));
    if(q.type==='mcq'){
      q.options.forEach((choice,i)=>{const label=el('label','opt');const input=el('input');input.type='radio';input.name=q.id;input.value=String(i);input.checked=saved[q.id]===i;input.addEventListener('change',saveDraft);label.appendChild(input);label.appendChild(el('span','',choice));card.appendChild(label)});
    }else{
      card.appendChild(el('p','muted','Explain your reasoning, show calculations and give a scenario-specific conclusion where requested.'));
      const ta=el('textarea');ta.id='ans-'+q.id;ta.placeholder='Write your exam-style answer and workings here...';ta.value=saved[q.id]||'';ta.maxLength=12000;ta.addEventListener('input',saveDraft);card.appendChild(ta);
    }
    container.appendChild(card);
  });
  document.getElementById('confirm').checked=false;document.getElementById('validation').textContent='';
  show('exam');updateAnswered();startTimer();
}
async function loadList(){
  const [catalog,history]=await Promise.all([api('/api/topic-tests'),api('/api/topic-tests/history')]);
  const list=document.getElementById('catalog');list.replaceChildren();
  catalog.quizzes.forEach(q=>{const c=el('article','card');c.appendChild(el('h2','',q.title));c.appendChild(el('p','muted',q.description||''));c.appendChild(el('span','pill',q.total_marks+' marks'));c.appendChild(el('span','pill',q.duration_minutes+' min'));c.appendChild(el('span','pill',q.topic));const div=el('div','actions');const btn=el('button','', 'Start / resume test');btn.onclick=()=>openQuiz(q.id).catch(report);div.appendChild(btn);c.appendChild(div);list.appendChild(c)});
  if(!catalog.quizzes.length)list.appendChild(el('p','muted','No topic tests published yet.'));
  const hist=document.getElementById('history');hist.replaceChildren();
  history.attempts.forEach(a=>{const c=el('div','card');c.appendChild(el('b','',a.quiz_title));c.appendChild(el('p','muted',niceDate(a.submitted_at)+' · MCQs '+a.objective_score+'/'+a.objective_max+' · Written pending tutor marking'));const b=el('button','secondary','Review attempt');b.onclick=()=>showAttempt(a.id).catch(report);c.appendChild(b);hist.appendChild(c)});
  if(!history.attempts.length)hist.appendChild(el('div','card muted','No submissions yet.'));
}
async function showAttempt(id){
  const data=await api('/api/topic-tests/submissions/'+id);reviewRecord=data;
  const target=document.getElementById('reviewContent');target.replaceChildren();
  target.appendChild(el('h1','',data.quiz_title));
  target.appendChild(el('div','result','Objective score: '+data.objective_score+'/'+data.objective_max));
  target.appendChild(el('p','muted','Written responses are saved for tutor marking. This is not a final 40-mark grade.'));
  data.answers.forEach((a,index)=>{
    const section=el('div','card');section.appendChild(el('b','',String(index+1)+'. '+a.prompt));
    if(a.type==='mcq'){section.appendChild(el('p','', 'Your answer: '+(a.selected_text||'Not answered')));
      section.appendChild(el('p',a.correct?'good':'error',a.correct?'Correct (2/2)':'Incorrect (0/2)'));
      if(!a.correct)section.appendChild(el('p','muted','Correct answer: '+a.correct_text));
      section.appendChild(el('p','muted',a.explanation||''));
    }else{section.appendChild(el('div','pre',a.written||''));section.appendChild(el('p','muted','Pending examiner marking · '+a.marks+' available marks'))}
    target.appendChild(section);
  });
  const b=el('button','secondary','Copy submission for tutor marking');
  b.onclick=async()=>{const printable=JSON.stringify(data,null,2);try{await navigator.clipboard.writeText(printable);b.textContent='Copied for tutor marking'}catch(e){const t=el('textarea');t.value=printable;target.appendChild(t);t.select();b.textContent='Select and copy answer text below'}};
  target.appendChild(b);
  show('review');
}
function report(e){alert(e.message||String(e))}
document.getElementById('exit').onclick=()=>{if(ticker)clearInterval(ticker);active=null;loadList().then(()=>show('intro')).catch(report)};
document.getElementById('backHistory').onclick=()=>{loadList().then(()=>show('intro')).catch(report)};
document.getElementById('submit').onclick=async()=>{
  if(!active)return;
  const answers={};const missing=[];
  active.questions.forEach((q,i)=>{if(q.type==='mcq'){const x=document.querySelector('input[name="'+q.id+'"]:checked');if(x)answers[q.id]=Number(x.value);else missing.push(i+1)}else{const t=document.getElementById('ans-'+q.id);if(t&&t.value.trim())answers[q.id]=t.value.trim();else missing.push(i+1)}});
  if(missing.length){document.getElementById('validation').textContent='Answer all questions. Missing: '+missing.join(', ');return}
  if(!document.getElementById('confirm').checked){document.getElementById('validation').textContent='Confirm you are ready to submit.';return}
  if(!confirm('Submit this attempt? You can view your results and written answers afterwards.'))return;
  const btn=document.getElementById('submit');btn.disabled=true;
  try{
    const r=await api('/api/topic-tests/'+active.id+'/submit',{method:'POST',body:JSON.stringify({answers:answers})});
    localStorage.removeItem(draftKey());localStorage.removeItem(timeKey());if(ticker)clearInterval(ticker);active=null;
    await showAttempt(r.attempt_id);
  }catch(e){report(e)}finally{btn.disabled=false}
};
loadList().catch(report);
})();
</script></body></html>"""


def register_topic_tests(app, db_connect, current_user, csrf_token):
    def get_quizzes():
        with QUESTION_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data.get("quizzes", [])

    def login_or_none():
        return current_user()

    def require_user():
        user = login_or_none()
        if not user:
            abort(401)
        return user

    def safe_submit():
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            abort(403, "Invalid session token")

    def init_topic_db():
        conn = db_connect()
        conn.execute("""CREATE TABLE IF NOT EXISTS topic_quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quiz_id TEXT NOT NULL,
            quiz_title TEXT NOT NULL,
            quiz_snapshot TEXT NOT NULL,
            submitted_answers TEXT NOT NULL,
            objective_score INTEGER NOT NULL,
            objective_max INTEGER NOT NULL,
            submitted_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_attempts_user ON topic_quiz_attempts(user_id, submitted_at)")
        conn.commit()
        conn.close()

    init_topic_db()

    @app.get("/topic-tests")
    def topic_tests_page():
        if not login_or_none():
            return redirect(url_for("login"))
        return render_template_string(PAGE, csrf=csrf_token())

    @app.get("/api/topic-tests")
    def topic_tests_catalog():
        require_user()
        quizzes = get_quizzes()
        return jsonify({"quizzes": [
            {"id": q["id"], "title": q["title"], "description": q.get("description", ""),
             "duration_minutes": q.get("duration_minutes", 50),
             "topic": q.get("topic", ""),
             "total_marks": sum(item["marks"] for item in q["questions"])}
            for q in quizzes if q.get("published", True)
        ]})

    @app.get("/api/topic-tests/<quiz_id>")
    def topic_test_questions(quiz_id):
        user = require_user()
        q = next((x for x in get_quizzes() if x["id"] == quiz_id and x.get("published", True)), None)
        if not q:
            abort(404)
        questions = [
            {"id": item["id"], "type": item["type"], "marks": item["marks"],
             "prompt": item["prompt"], **({"options": item["options"]} if item["type"] == "mcq" else {})}
            for item in q["questions"]
        ]
        return jsonify({"quiz": {
            "id": q["id"], "title": q["title"], "duration_minutes": q.get("duration_minutes", 50),
            "questions": questions}, "user_key": str(user["id"])})

    @app.get("/api/topic-tests/history")
    def topic_tests_history():
        user = require_user()
        conn = db_connect()
        rows = conn.execute(
            """SELECT id, quiz_id, quiz_title, objective_score, objective_max, submitted_at
               FROM topic_quiz_attempts WHERE user_id=? ORDER BY id DESC LIMIT 100""",
            (user["id"],)
        ).fetchall()
        conn.close()
        return jsonify({"attempts": [dict(x) for x in rows]})

    @app.post("/api/topic-tests/<quiz_id>/submit")
    def topic_tests_submit(quiz_id):
        user = require_user()
        safe_submit()
        q = next((x for x in get_quizzes() if x["id"] == quiz_id and x.get("published", True)), None)
        if not q:
            abort(404)
        payload = request.get_json(silent=True) or {}
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            return jsonify({"error": "Missing answers."}), 400
        if set(answers.keys()) != {item["id"] for item in q["questions"]}:
            return jsonify({"error": "Every question requires an answer."}), 400
        objective_score = objective_max = 0
        for item in q["questions"]:
            v = answers[item["id"]]
            if item["type"] == "mcq":
                objective_max += int(item["marks"])
                if type(v) is not int or v < 0 or v >= len(item["options"]):
                    return jsonify({"error": "Invalid MCQ answer."}), 400
                if v == item["answer"]:
                    objective_score += int(item["marks"])
            else:
                if not isinstance(v, str) or not v.strip() or len(v) > 12000:
                    return jsonify({"error": "Written answers must be between 1 and 12000 characters."}), 400
        conn = db_connect()
        cur = conn.execute(
            """INSERT INTO topic_quiz_attempts
               (user_id,quiz_id,quiz_title,quiz_snapshot,submitted_answers,objective_score,objective_max,submitted_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (user["id"], quiz_id, q["title"], json.dumps(q), json.dumps(answers),
             objective_score, objective_max, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        )
        conn.commit()
        attempt_id = cur.lastrowid
        conn.close()
        return jsonify({"attempt_id": attempt_id, "objective_score": objective_score,
                        "objective_max": objective_max, "written_status": "pending tutor marking"})

    @app.get("/api/topic-tests/submissions/<int:attempt_id>")
    def topic_test_review(attempt_id):
        user = require_user()
        conn = db_connect()
        row = conn.execute("SELECT * FROM topic_quiz_attempts WHERE id=? AND user_id=?",
                           (attempt_id, user["id"])).fetchone()
        conn.close()
        if not row:
            abort(404)
        q = json.loads(row["quiz_snapshot"])
        submitted = json.loads(row["submitted_answers"])
        items = []
        for question in q["questions"]:
            ans = submitted[question["id"]]
            item = {"type": question["type"], "prompt": question["prompt"], "marks": question["marks"]}
            if question["type"] == "mcq":
                item.update({"selected_text": question["options"][ans], "correct": ans == question["answer"],
                             "correct_text": question["options"][question["answer"]],
                             "explanation": question.get("explanation", "")})
            else:
                item["written"] = ans
            items.append(item)
        return jsonify({"id": row["id"], "quiz_id": row["quiz_id"], "quiz_title": row["quiz_title"],
                        "submitted_at": row["submitted_at"], "objective_score": row["objective_score"],
                        "objective_max": row["objective_max"], "answers": items,
                        "written_status": "pending tutor marking"})
