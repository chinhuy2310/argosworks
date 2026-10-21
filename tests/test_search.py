import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from services.search import search_records

class TestSearch(unittest.TestCase):
    def test_search_scoring_title_weight(self):
        records = [
            {"id": "1", "title": "Security vulnerability patch", "memo": "minor details", "assignee": "Alice"},
            {"id": "2", "title": "Regular meeting", "memo": "we talked about security briefly", "assignee": "Bob"},
        ]
        results = search_records(records, "security")
        self.assertTrue(len(results) >= 1)
        # Record 1 should be ranked higher because match in title has higher weight (4.0x vs 1.0x)
        self.assertEqual(results[0]["id"], "1")

if __name__ == "__main__":
    unittest.main()
