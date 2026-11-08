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

body{display:flex;min-height:100vh}
.portalSide{width:220px;flex:0 0 220px;height:100vh;position:sticky;top:0;background:#103a5c;color:#d6ecfa;display:flex;flex-direction:column;padding:18px 12px;gap:6px;overflow-y:auto}
.portalBrand{color:#fff;font-size:20px;font-weight:900;padding:6px 10px 17px}
.portalSide a{text-decoration:none;color:#cce2f3;font-size:13px;font-weight:700;padding:12px 13px;border-radius:8px;display:flex;justify-content:space-between;gap:5px}
.portalSide a:hover,.portalSide a[aria-current="page"]{background:#19618e;color:#fff}
.portalSide small{font-size:10px;color:#a7c6d9;line-height:1.5;padding:15px 10px;margin-top:auto}
.portalShell{flex:1;min-width:0}
.topicExamLayout{display:grid;grid-template-columns:212px minmax(0,1fr);gap:15px;align-items:start}
.topicExamNav{position:sticky;top:90px;max-height:calc(100vh - 110px);overflow:auto}
.topicNavGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:12px 0}
.topicNavChip{border:1px solid #b9cad6;background:#f4f8fa;color:#28516a;border-radius:8px;padding:9px 0;font-size:13px}
.topicNavChip.current{background:#0a6ca8;border-color:#0a6ca8;color:#fff}
.topicNavChip.answered{border-color:#57aa84}
.topicNavChip.flagged:after{content:" ⚑";font-size:9px}
.topicNavLegend{font-size:11px;color:#637f92;line-height:1.5}
.topicExamBody{min-width:0}
.topicExamBody .question{display:none}
.topicExamBody .question.current{display:block}
.topicExamActions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.topicExamActions .right{margin-left:auto}
#submitArea{margin-top:12px}
#submitArea button{background:#126a4e}
#submitArea .error{margin-top:10px}
.topicNavToggle{display:none}
@media(max-width:1000px){.portalSide{width:180px;flex-basis:180px}.topicExamLayout{grid-template-columns:180px minmax(0,1fr)}}
@media(max-width:760px){
 body{display:block}.portalSide{width:100%;height:auto;position:static;flex-direction:row;overflow:auto;white-space:nowrap;padding:8px}
 .portalBrand{font-size:14px;padding:9px}.portalSide a{padding:9px;font-size:12px}
 .portalSide small{display:none}.topicExamLayout{display:block}
 .topicExamNav{position:static;max-height:none;display:none}.topicExamNav.open{display:block}
 .topicNavToggle{display:inline-block}.wrap{padding:12px}.card{padding:15px}header{padding:13px}.toolbar{position:static}
}

</style></head><body data-csrf="{{ csrf }}">
<nav class="portalSide" aria-label="F7 portal sections">
<div class="portalBrand">ACCA FR / F7</div>
<a href="/?panel=overview">Dashboard <span>›</span></a>
<a href="/?panel=mocks">Mock Exams <span>›</span></a>
<a href="/topic-tests" aria-current="page">Topic Tests <span>›</span></a>
<a href="/?panel=history">Mock History <span>›</span></a>
<a href="/?panel=retests">Retests <span>›</span></a>
<a href="/?panel=analytics">Analytics <span>›</span></a>
<a href="/?panel=progress">Progress <span>›</span></a>
<a href="/?panel=management">Management <span>›</span></a>
<small>Your submitted attempts are saved to your account. Draft answers remain in this browser until submission.</small>
</nav>
<div class="portalShell">
<header><strong>ACCA FR / F7</strong><span>Topic Tests</span><span class="push"></span><a href="/?panel=overview">Home</a></header>
<main class="wrap"><section id="intro"><h1>Chapter practice tests</h1>
<p class="muted">Complete all objective and written answers on this site. MCQs are marked on submission; written answers are saved for strict tutor marking. Past attempts remain accessible.</p>
<div id="catalog" class="grid"></div>
<h2>Your previous submissions</h2><div id="history"></div></section>
<section id="exam" class="hidden">
<div class="toolbar">
<div class="topicExamActions"><button class="secondary" id="exit">Save & Back to Tests</button><button class="secondary" id="exitHome">Save & Exit to Home</button><button class="secondary topicNavToggle" id="navToggle">Navigator</button></div>
<div><b id="examTitle"></b><span class="pill" id="timer">50:00</span></div><span id="answered" class="muted"></span>
</div>
<div class="card"><p class="muted">12 MCQs × 2 marks + 2 written × 8 marks = 40 marks. Skip does not submit or score your test. Draft answers autosave in this browser. Only Submit records a graded attempt.</p></div>
<div class="topicExamLayout">
<aside id="topicNav" class="topicExamNav card" aria-label="Question navigator">
<strong>Question Navigator</strong><p id="qPosition" class="muted">Question 1 of 14</p>
<div id="qNavGrid" class="topicNavGrid"></div>
<p class="topicNavLegend">Blue: current. Green border: answered. Flag: review later.</p>
<button class="secondary" id="navClose">Close Navigator</button>
</aside>
<div class="topicExamBody">
<div id="questions"></div>
<div class="card topicExamActions">
<button class="secondary" id="qPrev">← Previous</button>
<button class="secondary" id="qFlag">Flag for Review</button>
<div class="right"></div>
<button class="secondary" id="qSkip">Skip →</button>
<button id="qNext">Next →</button>
</div>
<div class="card" id="submitArea"><label><input type="checkbox" id="confirm"> I have answered all questions and want to submit this attempt for marking.</label>
<div class="actions"><button id="submit">Submit for marking</button></div><div id="validation" class="error" role="alert"></div></div>
</div></div>
</section>
<section id="review" class="hidden"><button class="secondary" id="backHistory">Back to Topic Tests</button><div class="card" id="reviewContent"></div></section>
</main></div>
<script>
(function(){
'use strict';
const csrf=document.body.dataset.csrf;
const intro=document.getElementById('intro'),exam=document.getElementById('exam'),review=document.getElementById('review');
let active=null,startTime=null,ticker=null,userKey=null,reviewRecord=null,currentIndex=0,flags={};
const el=(tag,cls,txt)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(txt!==undefined)x.textContent=txt;return x;};
const show=(which)=>{intro.classList.toggle('hidden',which!=='intro');exam.classList.toggle('hidden',which!=='exam');review.classList.toggle('hidden',which!=='review');window.scrollTo(0,0)};
const niceDate=(s)=>{try{return new Date(s).toLocaleString()}catch(e){return s}};
async function api(path,opts){const res=await fetch(path,Object.assign({credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}},opts||{}));const body=await res.json();if(!res.ok)throw new Error(body.error||'Request failed');return body}
const draftKey=()=> 'fr-topic-draft:'+userKey+':'+active.id;
const timeKey=()=> 'fr-topic-start:'+userKey+':'+active.id;
const flagKey=()=> 'fr-topic-flags:'+userKey+':'+active.id;
function saveDraft(){if(!active)return;const answers={};active.questions.forEach(q=>{if(q.type==='mcq'){const x=document.querySelector('input[name="'+q.id+'"]:checked');if(x)answers[q.id]=Number(x.value)}else{const t=document.getElementById('ans-'+q.id);answers[q.id]=t?t.value:''}});localStorage.setItem(draftKey(),JSON.stringify(answers));updateAnswered();renderQuestionNav()}
function readDraft(){try{return JSON.parse(localStorage.getItem(draftKey())||'{}')}catch(e){return {}}}
function updateAnswered(){if(!active)return;let n=0;active.questions.forEach(q=>{if(q.type==='mcq'){if(document.querySelector('input[name="'+q.id+'"]:checked'))n++}else{const t=document.getElementById('ans-'+q.id);if(t&&t.value.trim())n++}});document.getElementById('answered').textContent=n+'/'+active.questions.length+' answered'}
function startTimer(){if(ticker)clearInterval(ticker);let saved=localStorage.getItem(timeKey());if(!saved||!Number(saved)){saved=String(Date.now());localStorage.setItem(timeKey(),saved)}startTime=Number(saved);const update=()=>{const seconds=Math.max(0,(active.duration_minutes||50)*60-Math.floor((Date.now()-startTime)/1000));document.getElementById('timer').textContent=(seconds<=0?'Time elapsed · ':'')+String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');};update();ticker=setInterval(update,1000)}

function questionAnswered(q){
  if(q.type==='mcq')return !!document.querySelector('input[name="'+q.id+'"]:checked');
  const t=document.getElementById('ans-'+q.id);return !!(t&&t.value.trim());
}
function renderQuestionNav(){
  if(!active)return;
  const nav=document.getElementById('qNavGrid');nav.replaceChildren();
  active.questions.forEach((q,i)=>{
    const btn=el('button','topicNavChip',String(i+1));
    btn.classList.toggle('current',i===currentIndex);
    btn.classList.toggle('answered',questionAnswered(q));
    btn.classList.toggle('flagged',!!flags[q.id]);
    btn.title='Question '+(i+1)+(questionAnswered(q)?' · answered':' · unanswered')+(flags[q.id]?' · flagged':'');
    btn.type='button';btn.onclick=()=>gotoQuestion(i);nav.appendChild(btn);
  });
  document.getElementById('qPosition').textContent='Question '+(currentIndex+1)+' of '+active.questions.length;
  document.getElementById('qPrev').disabled=currentIndex===0;
  document.getElementById('qNext').disabled=currentIndex===active.questions.length-1;
  document.getElementById('qSkip').disabled=currentIndex===active.questions.length-1;
  document.getElementById('qFlag').textContent=flags[active.questions[currentIndex].id]?'⚑ Remove Flag':'⚑ Flag for Review';
}
function gotoQuestion(i){
  if(!active)return;
  currentIndex=Math.min(active.questions.length-1,Math.max(0,i));
  document.querySelectorAll('#questions .question').forEach((card,j)=>card.classList.toggle('current',j===currentIndex));
  renderQuestionNav();
  window.scrollTo({top:0,behavior:'instant'});
}
function toggleQuestionFlag(){
  if(!active)return;
  const id=active.questions[currentIndex].id;flags[id]=!flags[id];
  localStorage.setItem(flagKey(),JSON.stringify(flags));renderQuestionNav();
}
function leaveTopicTest(home){
  if(!active){if(home)window.location.assign('/?panel=overview');else show('intro');return}
  saveDraft();
  if(!confirm('Your answers are saved as a draft in this browser. Exit without submitting or recording a score?'))return;
  if(ticker)clearInterval(ticker);active=null;
  if(home){window.location.assign('/?panel=overview');return}
  loadList().then(()=>show('intro')).catch(report);
}
document.addEventListener('keydown',function(ev){
  if(!active||exam.classList.contains('hidden')||ev.altKey||ev.ctrlKey||ev.metaKey)return;
  if(ev.target.closest('input,textarea,select,[contenteditable]'))return;
  if(ev.key==='ArrowRight'){ev.preventDefault();gotoQuestion(currentIndex+1)}
  else if(ev.key==='ArrowLeft'){ev.preventDefault();gotoQuestion(currentIndex-1)}
});
window.addEventListener('pagehide',function(){if(active)saveDraft()});
document.getElementById('qPrev').onclick=()=>gotoQuestion(currentIndex-1);
document.getElementById('qNext').onclick=()=>gotoQuestion(currentIndex+1);
document.getElementById('qSkip').onclick=()=>gotoQuestion(currentIndex+1);
document.getElementById('qFlag').onclick=toggleQuestionFlag;
document.getElementById('exitHome').onclick=()=>leaveTopicTest(true);
document.getElementById('navToggle').onclick=()=>document.getElementById('topicNav').classList.toggle('open');
document.getElementById('navClose').onclick=()=>document.getElementById('topicNav').classList.remove('open');
document.querySelectorAll('.portalSide a,header a').forEach(a=>a.addEventListener('click',function(ev){
 if(!active)return;ev.preventDefault();saveDraft();
 if(!confirm('Exit this unfinished topic test without submitting? Your answers are saved as a draft in this browser.'))return;
 window.location.assign(a.href);
}));

async function openQuiz(id){
  const data=await api('/api/topic-tests/'+encodeURIComponent(id));active=data.quiz;userKey=data.user_key;
  document.getElementById('examTitle').textContent=active.title;
  const container=document.getElementById('questions');container.replaceChildren();
  const saved=readDraft();currentIndex=0;try{flags=JSON.parse(localStorage.getItem(flagKey())||'{}')}catch(e){flags={}}
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
  show('exam');gotoQuestion(0);updateAnswered();startTimer();
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
document.getElementById('exit').onclick=()=>leaveTopicTest(false);
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
    localStorage.removeItem(draftKey());localStorage.removeItem(timeKey());localStorage.removeItem(flagKey());if(ticker)clearInterval(ticker);active=null;
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
