# -*- coding: utf-8 -*-
"""Regression tests for the central RBAC layer (viewer read-only + record ownership + IDOR).

These tests are self-contained: they create their own users/records/notifications and
clean them up, so they can run on a fresh CI database.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from db import init_db, execute, query, get_one
from services.auth import is_viewer, can_write_data, check_record_write_access
from services.data_store import append_record, delete_record, update_record_work_date
from handlers.schedule_handlers import (
    handle_schedule_create, handle_schedule_update, handle_schedule_delete,
)
from handlers.department_handler import handle_delete_department
from router import (
    handle_assign_schedule_task, handle_unassign_schedule_task,
    handle_post_issue_attachment, handle_push_record_jira,
    handle_post_notification_read,
)
from config import ATTACH_DIR

USER_IDS = {"admin": 997201, "manager": 997202, "member": 997203, "viewer": 997204, "other": 997205}
USERNAMES = {"admin": "rbac_m_admin", "manager": "rbac_m_manager", "member": "rbac_m_member",
             "viewer": "rbac_m_viewer", "other": "rbac_m_other"}
REC_ID = 997701
REC_ID_OWNED = 997702


def session(role, name, user_key, dept, email):
    uid = USER_IDS[user_key]
    return {"id": uid, "user_id": uid, "username": USERNAMES[user_key], "name": name,
            "role": role, "org": dept, "dept_id": dept, "email": email,
            "is_admin": 1 if role == "admin" else 0}


ADMIN = session("admin", "RBAC Admin", "admin", "mgmt", "rbac_admin@test.local")
MANAGER = session("manager", "RBAC Manager", "manager", "dev", "rbac_mgr@test.local")
MEMBER = session("member", "RBAC Member", "member", "dev", "rbac_member@test.local")
VIEWER = session("viewer", "RBAC Viewer", "viewer", "dev", "rbac_viewer@test.local")
OTHER = session("member", "RBAC Other", "other", "dev", "rbac_other@test.local")


class MockHandler:
    def __init__(self, sess, content_type="application/json"):
        self.session = sess
        self.status = None
        self.body = None
        self.cfg = {"jira": {"enabled": False, "api_token": ""}}
        self.headers = {"Content-Type": content_type}

    def _get_session_or_401(self):
        if not self.session:
            self._send_json(401, {"ok": False, "error": "로그인이 필요합니다."})
            return None
        return self.session

    def _send_json(self, status, payload, extra_headers=None):
        self.status = status
        self.body = payload


def _record(rec_id, assignee):
    return {
        "id": rec_id,
        "org": "dev",
        "category": "개발",
        "title": "RBAC Fixture %d" % rec_id,
        "project": "RBAC",
        "assignee": assignee,
        "assigneeEmail": "rbac_other@test.local" if assignee == "RBAC Other" else "rbac_member@test.local",
        "startDate": "2026-10-20",
        "dueDate": "2026-10-21",
        "summary": "",
        "tags": ["개발"],
        "memo": "",
        "cardCode": "RBAC-%d" % rec_id,
        "participants": "",
        "parentKey": "",
        "jira": None,
    }


def _multipart(issue_key, filename="rbac.txt", content=b"rbac"):
    boundary = "----rbacBoundary"
    body = (
        '--%s\r\nContent-Disposition: form-data; name="issue_key"\r\n\r\n%s\r\n'
        '--%s\r\nContent-Disposition: form-data; name="files"; filename="%s"\r\n'
        'Content-Type: text/plain\r\n\r\n' % (boundary, issue_key, boundary, filename)
    ).encode() + content + ("\r\n--%s--\r\n" % boundary).encode()
    return body, "multipart/form-data; boundary=%s" % boundary


class TestRbacMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        # Không phụ thuộc license thật: giả lập license còn hạn
        self.license_patch = patch("services.license_manager.is_system_read_only", return_value=False)
        self.license_patch.start()

        execute("DELETE FROM users WHERE username LIKE 'rbac_m_%'")
        rows = [
            (997201, "rbac_m_admin", "RBAC Admin", "mgmt", "rbac_admin@test.local", 1, "admin"),
            (997202, "rbac_m_manager", "RBAC Manager", "dev", "rbac_mgr@test.local", 0, "manager"),
            (997203, "rbac_m_member", "RBAC Member", "dev", "rbac_member@test.local", 0, "member"),
            (997204, "rbac_m_viewer", "RBAC Viewer", "dev", "rbac_viewer@test.local", 0, "viewer"),
            (997205, "rbac_m_other", "RBAC Other", "dev", "rbac_other@test.local", 0, "member"),
        ]
        for uid, username, name, dept, email, is_admin, role in rows:
            # INSERT (không OR REPLACE) để không bao giờ ghi đè user thật trùng username
            execute("""INSERT INTO users
                       (id, username, name, dept_id, email, is_admin, role, disabled, status, salt, password_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'active', 's', 'p')""",
                    (uid, username, name, dept, email, is_admin, role))

        execute("DELETE FROM records WHERE id >= 997700")
        execute("DELETE FROM notifications WHERE id LIKE 'rbac_notif_%'")
        execute("DELETE FROM schedule_events WHERE title LIKE 'RBAC-SCHED%'")
        append_record(_record(REC_ID, "RBAC Other"))
        append_record(_record(REC_ID_OWNED, "RBAC Member"))

    def tearDown(self):
        self.license_patch.stop()
        execute("DELETE FROM record_attachments WHERE record_id >= 997700")
        execute("DELETE FROM records WHERE id >= 997700")
        execute("DELETE FROM users WHERE username LIKE 'rbac_m_%'")
        execute("DELETE FROM notifications WHERE id LIKE 'rbac_notif_%'")
        execute("DELETE FROM schedule_events WHERE title LIKE 'RBAC-SCHED%'")
        for rid in (REC_ID, REC_ID_OWNED):
            for fname in ("rbac.txt", "rbac-owned.txt"):
                path = os.path.join(ATTACH_DIR, str(rid), fname)
                if os.path.exists(path):
                    os.remove(path)

    # ------------------------------------------------------------------ helpers
    def test_role_helpers(self):
        self.assertTrue(is_viewer(VIEWER))
        self.assertFalse(is_viewer(MEMBER))
        self.assertFalse(can_write_data(VIEWER))
        self.assertTrue(can_write_data(MEMBER))
        self.assertTrue(can_write_data(MANAGER))
        self.assertTrue(can_write_data(ADMIN))
        self.assertFalse(can_write_data(None))

    # ------------------------------------------------------------------ schedule
    def test_viewer_cannot_create_schedule(self):
        handler = MockHandler(VIEWER)
        handle_schedule_create(handler, b'{"title":"RBAC-SCHED-V","type":"meeting",'
                                        b'"startDate":"2026-10-25","endDate":"2026-10-25"}', "127.0.0.1")
        self.assertEqual(handler.status, 403)
        self.assertEqual(query("SELECT id FROM schedule_events WHERE title = 'RBAC-SCHED-V'"), [])

    def test_viewer_cannot_update_or_delete_schedule(self):
        creator = MockHandler(MEMBER)
        handle_schedule_create(creator, b'{"title":"RBAC-SCHED-M","type":"meeting",'
                                        b'"startDate":"2026-10-25","endDate":"2026-10-25"}', "127.0.0.1")
        self.assertEqual(creator.status, 200, creator.body)
        event_id = creator.body["event"]["id"]

        updater = MockHandler(VIEWER)
        handle_schedule_update(updater, ('{"id": %s, "title":"hack","type":"meeting",'
                                         '"startDate":"2026-10-26","endDate":"2026-10-26"}' % event_id).encode(),
                               "127.0.0.1")
        self.assertEqual(updater.status, 403)

        deleter = MockHandler(VIEWER)
        handle_schedule_delete(deleter, ('{"id": %s}' % event_id).encode(), "127.0.0.1")
        self.assertEqual(deleter.status, 403)
        self.assertIsNotNone(get_one("SELECT id FROM schedule_events WHERE id = ?", (event_id,)))

        owner = MockHandler(MEMBER)
        handle_schedule_delete(owner, ('{"id": %s}' % event_id).encode(), "127.0.0.1")
        self.assertEqual(owner.status, 200)

    # ------------------------------------------------------- assign / unassign
    def test_assign_and_unassign_require_record_write_access(self):
        viewer = MockHandler(VIEWER)
        handle_assign_schedule_task(viewer, ('{"taskId":"%d","date":"2026-12-31"}' % REC_ID).encode(), "127.0.0.1")
        self.assertEqual(viewer.status, 403)

        member = MockHandler(MEMBER)
        handle_assign_schedule_task(member, ('{"taskId":"%d","date":"2026-12-31"}' % REC_ID).encode(), "127.0.0.1")
        self.assertEqual(member.status, 403)

        manager = MockHandler(MANAGER)
        handle_assign_schedule_task(manager, ('{"taskId":"%d","date":"2026-12-31"}' % REC_ID).encode(), "127.0.0.1")
        self.assertEqual(manager.status, 200, manager.body)
        row = get_one("SELECT start_date, due_date FROM records WHERE id = ?", (REC_ID,))
        self.assertEqual(row["start_date"], "2026-12-31")

        handle_unassign_schedule_task(viewer, ('{"taskId":"%d"}' % REC_ID).encode(), "127.0.0.1")
        self.assertEqual(viewer.status, 403)

        # khôi phục ngày gốc cho các test khác
        update_record_work_date(str(REC_ID), "2026-10-20", "2026-10-21")

    # --------------------------------------------------------------- attachments
    def test_attachment_upload_requires_record_write_access(self):
        body, ctype = _multipart(str(REC_ID), "rbac.txt")

        viewer = MockHandler(VIEWER, ctype)
        handle_post_issue_attachment(viewer, body, "127.0.0.1")
        self.assertEqual(viewer.status, 403)
        self.assertFalse(os.path.exists(os.path.join(ATTACH_DIR, str(REC_ID), "rbac.txt")))

        member = MockHandler(MEMBER, ctype)
        handle_post_issue_attachment(member, body, "127.0.0.1")
        self.assertEqual(member.status, 403)

        # Chủ sở hữu record (assignee) thì được phép
        body_owned, ctype_owned = _multipart(str(REC_ID_OWNED), "rbac-owned.txt")
        owner = MockHandler(MEMBER, ctype_owned)
        handle_post_issue_attachment(owner, body_owned, "127.0.0.1")
        self.assertEqual(owner.status, 200, owner.body)

    # ------------------------------------------------------------------ push jira
    def test_push_jira_requires_record_write_access(self):
        viewer = MockHandler(VIEWER)
        handle_push_record_jira(viewer, ('{"id":"%d"}' % REC_ID).encode(), "127.0.0.1")
        self.assertEqual(viewer.status, 403)

        member = MockHandler(MEMBER)
        handle_push_record_jira(member, ('{"id":"%d"}' % REC_ID).encode(), "127.0.0.1")
        self.assertEqual(member.status, 403)

        # Manager cùng phòng được qua lớp RBAC; Jira chưa cấu hình -> 400
        manager = MockHandler(MANAGER)
        handle_push_record_jira(manager, ('{"id":"%d"}' % REC_ID).encode(), "127.0.0.1")
        self.assertEqual(manager.status, 400, manager.body)

    # --------------------------------------------------------------- departments
    def test_department_management_is_admin_only(self):
        manager = MockHandler(MANAGER)
        handle_delete_department(manager, b'{"id":"dev"}', "127.0.0.1")
        self.assertEqual(manager.status, 403)

        execute("INSERT INTO departments (id, name) VALUES ('rbac_tmp_dept', 'RBAC Temp')")
        admin = MockHandler(ADMIN)
        handle_delete_department(admin, b'{"id":"rbac_tmp_dept"}', "127.0.0.1")
        self.assertEqual(admin.status, 200, admin.body)
        self.assertIsNone(get_one("SELECT id FROM departments WHERE id = 'rbac_tmp_dept'"))

        missing = MockHandler(ADMIN)
        handle_delete_department(missing, b'{"id":"rbac_no_such_dept"}', "127.0.0.1")
        self.assertEqual(missing.status, 404)

    # -------------------------------------------------------------- notifications
    def test_notification_read_enforces_ownership(self):
        execute("""INSERT INTO notifications
                   (id, recipient_email, recipient_name, sender_name, type, title, content, is_read)
                   VALUES ('rbac_notif_1', 'rbac_other@test.local', 'RBAC Other',
                           'RBAC Admin', 'assign', 'title', 'content', 0)""")

        stranger = MockHandler(MEMBER)
        handle_post_notification_read(stranger, b'{"id":"rbac_notif_1"}', "127.0.0.1")
        self.assertEqual(stranger.status, 404)
        self.assertEqual(get_one("SELECT is_read FROM notifications WHERE id = 'rbac_notif_1'")["is_read"], 0)

        owner = MockHandler(OTHER)
        handle_post_notification_read(owner, b'{"id":"rbac_notif_1"}', "127.0.0.1")
        self.assertEqual(owner.status, 200, owner.body)
        self.assertEqual(get_one("SELECT is_read FROM notifications WHERE id = 'rbac_notif_1'")["is_read"], 1)

        unknown = MockHandler(MEMBER)
        handle_post_notification_read(unknown, b'{"id":"rbac_notif_missing"}', "127.0.0.1")
        self.assertEqual(unknown.status, 404)


if __name__ == "__main__":
    unittest.main()


