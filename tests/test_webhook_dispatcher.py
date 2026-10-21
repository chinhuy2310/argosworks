import unittest
from unittest.mock import patch
import os
import sys

# Add server directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from services.webhook_dispatcher import (
    format_slack_payload,
    format_teams_payload,
    dispatch_notification_webhook
)

class TestWebhookDispatcher(unittest.TestCase):
    def test_format_slack_payload_colors(self):
        # Default blue
        p_info = format_slack_payload("New Task", "Task description", "Alice", link_id="101", tag="Normal")
        self.assertIn("*New Task*", p_info["text"])
        self.assertEqual(p_info["attachments"][0]["color"], "#3b82f6")

        # Urgent red
        p_urgent = format_slack_payload("Overdue Task", "Overdue", "Bob", link_id="102", tag="urgent")
        self.assertEqual(p_urgent["attachments"][0]["color"], "#ef4444")

        # D-Day amber
        p_dday = format_slack_payload("Deadline Today", "D-Day", "Charlie", link_id="103", tag="D-Day")
        self.assertEqual(p_dday["attachments"][0]["color"], "#f59e0b")

        # Done green
        p_done = format_slack_payload("Task Completed", "Done", "David", link_id="104", tag="완료")
        self.assertEqual(p_done["attachments"][0]["color"], "#10b981")

    def test_format_teams_payload_schema(self):
        p_teams = format_teams_payload("New Comment", "Please review", "Alice", link_id="205", tag="urgent")
        self.assertEqual(p_teams["@type"], "MessageCard")
        self.assertEqual(p_teams["themeColor"], "D83B01")
        self.assertIn("Alice", p_teams["sections"][0]["activitySubtitle"])
        facts = p_teams["sections"][0]["facts"]
        self.assertEqual(facts[0]["value"], "205")

    @patch("services.webhook_dispatcher._send_http_post")
    def test_dispatch_when_urls_configured(self, mock_send):
        with patch.dict(os.environ, {
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/test",
            "TEAMS_WEBHOOK_URL": "https://outlook.office.com/webhook/test"
        }):
            dispatch_notification_webhook("Notice", "Content", "System", "999", "info")
            # Webhook dispatch runs asynchronously in daemon thread, give it a tiny moment to execute
            import time
            time.sleep(0.1)
            self.assertEqual(mock_send.call_count, 2)

    @patch("services.webhook_dispatcher._send_http_post")
    def test_dispatch_when_no_urls(self, mock_send):
        with patch.dict(os.environ, {}, clear=True):
            dispatch_notification_webhook("Notice", "Content", "System", "999", "info")
            import time
            time.sleep(0.05)
            self.assertEqual(mock_send.call_count, 0)

if __name__ == "__main__":
    unittest.main()
