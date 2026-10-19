"""Server-side tests for the private chapter Study Board."""
import io
import tempfile
import unittest
from pathlib import Path

from flask import Flask
import board as study_board


class StudyBoardAPITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_store = study_board.STORE
        self.old_db = study_board.DB
        study_board.STORE = Path(self.temporary.name)
        study_board.DB = study_board.STORE / "study_board.sqlite3"
        study_board.init_board()
        self.app = Flask(__name__)
        self.app.register_blueprint(study_board.board)
        self.client = self.app.test_client()

    def tearDown(self):
        study_board.STORE = self.old_store
        study_board.DB = self.old_db
        self.temporary.cleanup()

    def test_chapter_context_validation(self):
        self.assertEqual(study_board.context({"subject": "AA", "chapter": "7"}), ("AA", "7"))
        self.assertEqual(study_board.context({"subject": "TX", "chapter": "1A"}), ("TX", "1A"))
        self.assertEqual(self.client.get("/study-board?subject=AA&chapter=../").status_code, 400)

    def test_upload_private_pdf_and_retrieve(self):
        response = self.client.post("/api/study-board/documents", data={
            "subject": "AA", "chapter": "7",
            "file": (io.BytesIO(b"%PDF-1.4\\nsmall-pdf-for-route-test"), "study.pdf"),
        })
        self.assertEqual(response.status_code, 201, response.data)
        document = response.get_json()["document"]
        listing = self.client.get("/api/study-board/documents?subject=AA&chapter=7").get_json()
        self.assertEqual(len(listing["documents"]), 1)
        other = self.client.get("/api/study-board/documents?subject=AA&chapter=6").get_json()
        self.assertEqual(len(other["documents"]), 0)
        content = self.client.get(document["view_url"])
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content.headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(content.data.startswith(b"%PDF-"))
        self.assertEqual(self.client.get(document["view_url"] + "?download=1").status_code, 200)

    def test_reject_non_pdf_masquerade(self):
        response = self.client.post("/api/study-board/documents", data={
            "subject": "AA", "chapter": "7",
            "file": (io.BytesIO(b"<html>not-pdf</html>"), "fake.pdf"),
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(list((study_board.STORE / "documents").iterdir()))

    def test_block_path_and_bad_extension(self):
        response = self.client.post("/api/study-board/documents", data={
            "subject": "TX", "chapter": "1B",
            "file": (io.BytesIO(b"print('bad')"), "../../notes.py"),
        })
        self.assertEqual(response.status_code, 400)

    def test_note_creation_read_and_edit(self):
        data = self.client.post("/api/study-board/notes", json={
            "subject": "TX", "chapter": "1A",
            "name": "My tax note", "text": "# Personal allowance\\n",
        })
        self.assertEqual(data.status_code, 201, data.data)
        document = data.get_json()["document"]
        content = self.client.get(document["view_url"])
        self.assertEqual(content.data.decode(), "# Personal allowance\\n")
        saved = self.client.put("/api/study-board/notes/" + document["id"],
                                json={"text": "# Updated\\nTax bands"})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(
            self.client.get(document["view_url"]).data.decode(), "# Updated\\nTax bands"
        )

    def test_create_update_conflict_and_reload_workbook(self):
        original = {"id": "test-1", "name": "Practice", "sheets": {
            "s1": {"id": "s1", "name": "Sheet1", "cellData": {}}}, "sheetOrder": ["s1"]}
        created = self.client.post("/api/study-board/workbooks", json={
            "subject": "AA", "chapter": "5", "name": "Risk analysis", "snapshot": original
        })
        self.assertEqual(created.status_code, 201, created.data)
        row = created.get_json()["workbook"]
        self.assertEqual(row["revision"], 1)
        updated = self.client.put("/api/study-board/workbooks/" + row["id"], json={
            "revision": 1, "name": "Risk 2026", "snapshot": {**original, "name": "Risk 2026"}
        })
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.get_json()["workbook"]["revision"], 2)
        conflict = self.client.put("/api/study-board/workbooks/" + row["id"], json={
            "revision": 1, "name": "Overwritten", "snapshot": original
        })
        self.assertEqual(conflict.status_code, 409)
        stored = self.client.get("/api/study-board/workbooks/" + row["id"])
        self.assertEqual(stored.get_json()["workbook"]["name"], "Risk 2026")
        self.assertEqual(stored.get_json()["workbook"]["snapshot"]["name"], "Risk 2026")
        self.assertEqual(
            len(self.client.get("/api/study-board/workbooks?subject=AA&chapter=5").get_json()["workbooks"]), 1
        )

    def test_cross_origin_upload_blocked(self):
        response = self.client.post("/api/study-board/notes",
            headers={"Origin": "http://evil.invalid"},
            json={"subject": "AA", "chapter": "1", "name": "Test", "text": "bad"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
