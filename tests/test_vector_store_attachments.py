# -*- coding: utf-8 -*-
"""Regression test: dong bo vector khong duoc crash khi record co attachment dang dict.

Bug goc: vector_store._collect_all_documents() dung ', '.join(attachments) trong khi
records.attachments la list[dict] ({"name": ...}) => TypeError: expected str instance.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from db import init_db, execute
from services.data_store import append_record
from services.vector_store import _collect_all_documents


class TestVectorStoreAttachments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        execute("DELETE FROM records WHERE id >= 998900")

    def tearDown(self):
        execute("DELETE FROM records WHERE id >= 998900")

    def _record(self, rec_id, attachments):
        return {
            "id": rec_id,
            "org": "dev",
            "category": "개발",
            "title": "Vector Attachment Test",
            "project": "Test Project",
            "assignee": "MemDev",
            "assigneeEmail": "memdev@test.com",
            "startDate": "2026-10-22",
            "dueDate": "2026-10-25",
            "summary": "Testing attachment embedding",
            "tags": ["개발"],
            "memo": "Memo content",
            "cardCode": "REC-%d" % rec_id,
            "participants": "",
            "parentKey": "",
            "attachments": attachments,
            "jira": None,
        }

    def test_record_attachments_are_indexed_without_type_error(self):
        rec_id = 998901
        # Production path: append_record() luu filename dang chuoi ...
        append_record(self._record(rec_id, ["spec sheet.pdf"]))

        # ... con read_records() tra ve list[dict] -> day chinh la hinh dang gay crash truoc day
        from services.data_store import read_records
        stored = next(r for r in read_records() if r.get("id") == rec_id)
        self.assertIsInstance(stored.get("attachments")[0], dict)

        docs = _collect_all_documents({})
        doc = next((d for d in docs if d.get("doc_id") == "record:%d" % rec_id), None)

        self.assertIsNotNone(doc, "record must be collected for embedding")
        self.assertIn("spec sheet.pdf", doc["content"])

    def test_empty_attachments_are_ignored(self):
        rec_id = 998902
        append_record(self._record(rec_id, []))

        docs = _collect_all_documents({})
        doc = next((d for d in docs if d.get("doc_id") == "record:%d" % rec_id), None)

        self.assertIsNotNone(doc)
        self.assertNotIn("첨부파일 목록", doc["content"])


if __name__ == "__main__":
    unittest.main()
