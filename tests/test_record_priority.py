import unittest
import os
import sys
import json

# Add server directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from db import init_db, execute, get_one, query
from services.data_store import append_record, get_record_by_id, update_record_details, find_record_by_key_or_code


class TestRecordPriority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        execute("DELETE FROM records WHERE id >= 998800")

    def tearDown(self):
        execute("DELETE FROM records WHERE id >= 998800")

    def test_default_priority_is_normal(self):
        rec_id = 998801
        rec = {
            "id": rec_id,
            "org": "dev",
            "category": "개발",
            "title": "Default Priority Test",
            "project": "Test Project",
            "assignee": "MemDev",
            "assigneeEmail": "memdev@test.com",
            "startDate": "2026-10-22",
            "dueDate": "2026-10-25",
            "summary": "Testing default priority",
            "tags": ["개발"],
            "memo": "Memo content",
            "cardCode": "REC-998801",
            "participants": "",
            "parentKey": "",
            "jira": None
        }
        append_record(rec)
        fetched = get_record_by_id(rec_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.get("priority"), "보통")

    def test_create_record_with_specific_priorities(self):
        priorities = ["낮음", "보통", "높음", "긴급"]
        for idx, prio in enumerate(priorities):
            rec_id = 998810 + idx
            rec = {
                "id": rec_id,
                "org": "dev",
                "category": "개발",
                "title": f"Priority Test {prio}",
                "project": "Test Project",
                "assignee": "MemDev",
                "assigneeEmail": "memdev@test.com",
                "startDate": "2026-10-22",
                "dueDate": "2026-10-25",
                "summary": f"Testing priority {prio}",
                "priority": prio,
                "cardCode": f"REC-{rec_id}",
                "jira": None
            }
            append_record(rec)
            fetched = get_record_by_id(rec_id)
            self.assertEqual(fetched.get("priority"), prio)

    def test_update_record_priority(self):
        rec_id = 998820
        rec = {
            "id": rec_id,
            "org": "dev",
            "category": "개발",
            "title": "Update Priority Test",
            "project": "Test Project",
            "assignee": "MemDev",
            "assigneeEmail": "memdev@test.com",
            "startDate": "2026-10-22",
            "dueDate": "2026-10-25",
            "priority": "보통",
            "cardCode": f"REC-{rec_id}",
            "jira": None
        }
        append_record(rec)
        
        # Update priority to 긴급
        updated, err = update_record_details(rec_id, priority="긴급")
        self.assertFalse(err)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.get("priority"), "긴급")

        # Update priority to 낮음
        updated2, err2 = update_record_details(rec_id, priority="낮음")
        self.assertFalse(err2)
        self.assertEqual(updated2.get("priority"), "낮음")

    def test_invalid_priority_fallback_to_normal(self):
        rec_id = 998830
        rec = {
            "id": rec_id,
            "org": "dev",
            "category": "개발",
            "title": "Invalid Priority Test",
            "priority": "HackedPriority",
            "cardCode": f"REC-{rec_id}",
            "jira": None
        }
        append_record(rec)
        fetched = get_record_by_id(rec_id)
        self.assertEqual(fetched.get("priority"), "보통")


if __name__ == "__main__":
    unittest.main()
