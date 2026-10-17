"""Private chapter-linked PDF/notes library and editable spreadsheet storage.

Files and workbooks belong to Jay's single-user Study Hub, not GitHub.
Set BOARD_STORAGE_PATH to a persistent writable directory in Bot-Hosting.
"""
import json
import mimetypes
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import is_zipfile

from flask import Blueprint, abort, jsonify, render_template, request, send_file

board = Blueprint("board", __name__)
STORE = Path(os.getenv("BOARD_STORAGE_PATH", str(Path(__file__).resolve().parent / "board_data")))
DB = STORE / "study_board.sqlite3"
MAX_UPLOAD = 32 * 1024 * 1024
MAX_SNAPSHOT = 9 * 1024 * 1024
FORMATS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}
SUBJECTS = {"AA", "TX"}
CHAPTER_RE = re.compile(r"^[0-9]{1,2}[A-Z]?$")
FILE_NAME_MAX = 120


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    con = sqlite3.connect(str(DB), timeout=20)
    con.row_factory = sqlite3.Row
    return con


def init_board():
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / "documents").mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS board_documents(
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                chapter TEXT NOT NULL,
                display_name TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL UNIQUE,
                mime TEXT NOT NULL,
                file_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS board_documents_chapter
                ON board_documents(subject, chapter, created_at);

            CREATE TABLE IF NOT EXISTS board_workbooks(
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                chapter TEXT NOT NULL,
                title TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS board_workbooks_chapter
                ON board_workbooks(subject, chapter, updated_at);
        """)


def context(params):
    subject = str(params.get("subject", "AA")).upper()
    chapter = str(params.get("chapter", "1")).upper()
    if subject not in SUBJECTS or not CHAPTER_RE.fullmatch(chapter):
        abort(400, description="A valid subject and chapter are required")
    if subject == "AA" and not chapter.isdigit():
        abort(400, description="AA chapter must be numeric")
    return subject, chapter


def origin_is_same_site():
    """Reject cross-origin unsafe requests when the browser supplies Origin."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    from urllib.parse import urlsplit
    try:
        url = urlsplit(origin)
        return url.scheme == request.scheme and url.netloc == request.host
    except ValueError:
        return False


def require_same_site():
    if not origin_is_same_site():
        abort(403)


def api_document(row):
    return {
        "id": row["id"], "subject": row["subject"], "chapter": row["chapter"],
        "name": row["display_name"], "filename": row["original_name"],
        "mime": row["mime"], "bytes": row["file_bytes"],
        "created_at": row["created_at"],
        "view_url": "/api/study-board/documents/" + row["id"] + "/content",
    }


def api_workbook(row, full=False):
    data = {
        "id": row["id"], "subject": row["subject"], "chapter": row["chapter"],
        "name": row["title"], "revision": row["revision"],
        "updated_at": row["updated_at"], "created_at": row["created_at"],
    }
    if full:
        data["snapshot"] = json.loads(row["snapshot"])
    return data


@board.get("/study-board")
def study_board():
    subject, chapter = context(request.args)
    return render_template("study_board.html", subject=subject, chapter=chapter)


@board.get("/api/study-board/documents")
def documents():
    subject, chapter = context(request.args)
    with connect() as con:
        rows = con.execute(
            """SELECT * FROM board_documents WHERE subject=? AND chapter=?
               ORDER BY created_at DESC, display_name ASC""", (subject, chapter)
        ).fetchall()
    items = [api_document(row) for row in rows]
    if subject == "TX":
        # Reuse existing TX notes without copying them into public uploads.
        from tx_hub import STUDY_NOTES
        if chapter in STUDY_NOTES:
            items.insert(0, {
                "id": "tx-built-in-" + chapter,
                "subject": subject, "chapter": chapter,
                "name": "Existing TX revision notes (" + chapter + ")",
                "filename": "TX_notes_" + chapter + ".md",
                "mime": "text/plain; charset=utf-8",
                "bytes": 0, "created_at": "", "builtin": True,
                "view_url": "/api/study-board/builtin/tx/" + chapter,
            })
    return jsonify({"documents": items})


@board.get("/api/study-board/builtin/tx/<code>")
def existing_tx_note(code):
    from tx_hub import STUDY_NOTES
    if code not in STUDY_NOTES:
        abort(404)
    text = "\n\n".join("## " + title + "\n\n" + explanation
                      for title, explanation in STUDY_NOTES[code])
    response = send_file(
        __import__("io").BytesIO(text.encode("utf-8")),
        mimetype="text/plain; charset=utf-8", download_name="TX_notes_" + code + ".md",
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@board.post("/api/study-board/documents")
def upload_document():
    require_same_site()
    subject, chapter = context(request.form)
    incoming = request.files.get("file")
    if incoming is None or not incoming.filename:
        return jsonify({"error": "Choose a PDF, note or spreadsheet file"}), 400
    basename = Path(incoming.filename.replace("\\", "/")).name[:FILE_NAME_MAX]
    extension = Path(basename).suffix.lower()
    if extension not in FORMATS:
        return jsonify({"error": "Supported: PDF, TXT, MD, CSV, XLSX or XLS"}), 400
    # Stream uploads in bounded chunks; don't read unbounded user content.
    identifier = uuid.uuid4().hex
    stored_name = identifier + extension
    dest = STORE / "documents" / stored_name
    total = 0
    try:
        with open(dest, "xb") as output:
            while True:
                chunk = incoming.stream.read(1024 * 512)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD:
                    return jsonify({"error": "File exceeds the 32 MB upload limit"}), 413
                output.write(chunk)
        if total == 0:
            return jsonify({"error": "The file is empty"}), 400
        with open(dest, "rb") as check:
            prefix = check.read(8)
        if extension == ".pdf" and not prefix.startswith(b"%PDF-"):
            return jsonify({"error": "Not a valid PDF file"}), 400
        if extension == ".xlsx" and not is_zipfile(dest):
            return jsonify({"error": "Not a valid XLSX file"}), 400

        display_name = request.form.get("name", "").strip()[:FILE_NAME_MAX] or basename
        with connect() as con:
            con.execute(
                """INSERT INTO board_documents
                (id,subject,chapter,display_name,original_name,stored_name,mime,file_bytes,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (identifier, subject, chapter, display_name, basename, stored_name,
                 FORMATS[extension], total, now()),
            )
        with connect() as con:
            row = con.execute("SELECT * FROM board_documents WHERE id=?", (identifier,)).fetchone()
        return jsonify({"document": api_document(row)}), 201
    finally:
        # If a validation error or database failure prevented insertion,
        # don't leave an unreferenced copy on disk.
        with connect() as con:
            saved = con.execute("SELECT 1 FROM board_documents WHERE id=?", (identifier,)).fetchone()
        if not saved:
            dest.unlink(missing_ok=True)


@board.get("/api/study-board/documents/<document_id>/content")
def download_document(document_id):
    if not re.fullmatch(r"[a-f0-9]{32}", document_id):
        abort(404)
    with connect() as con:
        row = con.execute("SELECT * FROM board_documents WHERE id=?", (document_id,)).fetchone()
    if not row:
        abort(404)
    file_path = STORE / "documents" / row["stored_name"]
    if not file_path.is_file():
        abort(404)
    response = send_file(
        file_path,
        mimetype=row["mime"],
        as_attachment=request.args.get("download") == "1" or row["mime"].startswith("application/vnd"),
        download_name=row["original_name"],
        conditional=True,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    if row["mime"].startswith("text/"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@board.delete("/api/study-board/documents/<document_id>")
def delete_document(document_id):
    require_same_site()
    with connect() as con:
        row = con.execute("SELECT stored_name FROM board_documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            abort(404)
        con.execute("DELETE FROM board_documents WHERE id=?", (document_id,))
    (STORE / "documents" / row["stored_name"]).unlink(missing_ok=True)
    return jsonify({"deleted": True})


@board.get("/api/study-board/workbooks")
def workbooks():
    subject, chapter = context(request.args)
    with connect() as con:
        rows = con.execute(
            """SELECT * FROM board_workbooks WHERE subject=? AND chapter=?
               ORDER BY updated_at DESC""", (subject, chapter)
        ).fetchall()
    return jsonify({"workbooks": [api_workbook(row) for row in rows]})


@board.post("/api/study-board/workbooks")
def create_workbook():
    require_same_site()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON expected"}), 400
    subject, chapter = context(payload)
    name = str(payload.get("name", "Study workbook")).strip()[:FILE_NAME_MAX]
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        return jsonify({"error": "A spreadsheet snapshot is required"}), 400
    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_SNAPSHOT:
        return jsonify({"error": "Workbook is too large"}), 413
    identifier = uuid.uuid4().hex
    timestamp = now()
    with connect() as con:
        con.execute(
            """INSERT INTO board_workbooks
               (id,subject,chapter,title,snapshot,revision,updated_at,created_at)
               VALUES (?,?,?,?,?,1,?,?)""",
            (identifier, subject, chapter, name or "Study workbook", serialized, timestamp, timestamp),
        )
        row = con.execute("SELECT * FROM board_workbooks WHERE id=?", (identifier,)).fetchone()
    return jsonify({"workbook": api_workbook(row, True)}), 201


@board.get("/api/study-board/workbooks/<workbook_id>")
def get_workbook(workbook_id):
    with connect() as con:
        row = con.execute("SELECT * FROM board_workbooks WHERE id=?", (workbook_id,)).fetchone()
    if not row:
        abort(404)
    response = jsonify({"workbook": api_workbook(row, True)})
    response.headers["Cache-Control"] = "private, no-store"
    return response


@board.put("/api/study-board/workbooks/<workbook_id>")
def update_workbook(workbook_id):
    require_same_site()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("snapshot"), dict):
        return jsonify({"error": "A spreadsheet snapshot is required"}), 400
    if type(payload.get("revision")) is not int:
        return jsonify({"error": "Revision required"}), 400
    serialized = json.dumps(payload["snapshot"], ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_SNAPSHOT:
        return jsonify({"error": "Workbook is too large"}), 413
    title = str(payload.get("name", "Study workbook")).strip()[:FILE_NAME_MAX]
    with connect() as con:
        existing = con.execute("SELECT * FROM board_workbooks WHERE id=?", (workbook_id,)).fetchone()
        if not existing:
            abort(404)
        if existing["revision"] != payload["revision"]:
            return jsonify({"error": "This workbook changed in another tab. Reload it before saving.", "revision": existing["revision"]}), 409
        con.execute(
            """UPDATE board_workbooks SET snapshot=?,title=?,revision=revision+1,updated_at=?
               WHERE id=? AND revision=?""",
            (serialized, title or existing["title"], now(), workbook_id, existing["revision"]),
        )
        row = con.execute("SELECT * FROM board_workbooks WHERE id=?", (workbook_id,)).fetchone()
    return jsonify({"workbook": api_workbook(row)})


init_board()


@board.post("/api/study-board/notes")
def create_note():
    """Create a private, editable chapter note (plain UTF-8 Markdown)."""
    require_same_site()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON expected"}), 400
    subject, chapter = context(payload)
    title = str(payload.get("name", "My notes")).strip()[:FILE_NAME_MAX] or "My notes"
    content = str(payload.get("text", ""))
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_UPLOAD:
        return jsonify({"error": "Note exceeds storage limit"}), 413
    identifier = uuid.uuid4().hex
    stored_name = identifier + ".md"
    path = STORE / "documents" / stored_name
    with open(path, "xb") as output:
        output.write(encoded)
    try:
        with connect() as con:
            con.execute(
                """INSERT INTO board_documents
                (id,subject,chapter,display_name,original_name,stored_name,mime,file_bytes,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (identifier, subject, chapter, title, title + ".md", stored_name,
                 FORMATS[".md"], len(encoded), now()),
            )
            row = con.execute("SELECT * FROM board_documents WHERE id=?", (identifier,)).fetchone()
        return jsonify({"document": api_document(row)}), 201
    except Exception:
        path.unlink(missing_ok=True)
        raise


@board.put("/api/study-board/notes/<document_id>")
def save_note(document_id):
    require_same_site()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        return jsonify({"error": "Text content expected"}), 400
    content = payload["text"].encode("utf-8")
    if len(content) > MAX_UPLOAD:
        return jsonify({"error": "Note exceeds storage limit"}), 413
    with connect() as con:
        row = con.execute("SELECT * FROM board_documents WHERE id=?", (document_id,)).fetchone()
        if not row or not row["stored_name"].endswith((".md", ".txt")):
            abort(404)
        destination = STORE / "documents" / row["stored_name"]
        temp = STORE / "documents" / (uuid.uuid4().hex + ".tmp")
        try:
            temp.write_bytes(content)
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)
        con.execute("UPDATE board_documents SET file_bytes=? WHERE id=?", (len(content), document_id))
    return jsonify({"saved": True, "bytes": len(content)})
