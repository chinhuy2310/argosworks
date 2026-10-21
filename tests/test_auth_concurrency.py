# -*- coding: utf-8 -*-
import unittest
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from db import init_db, execute, get_one, query
from services.auth import (
    create_user, get_user_by_login, get_user_by_id, safe_delete_user,
    hash_password, verify_password
)


class TestAuthConcurrencyAndSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        # Clean test records and users
        execute("DELETE FROM schedule_participants WHERE user_name LIKE 'test_%'")
        execute("DELETE FROM schedule_events WHERE title LIKE 'test_%'")
        execute("DELETE FROM records WHERE title LIKE 'test_%'")
        execute("DELETE FROM sessions WHERE user_name LIKE 'test_%'")
        execute("DELETE FROM users WHERE username LIKE 'test_%'")

    def tearDown(self):
        self.setUp()

    def test_create_user_and_get_by_login(self):
        salt, pwd_hash = hash_password("Password123!")
        user = create_user(
            name="Test User 1",
            username="test_user_1",
            org="dev",
            email="test_user_1@argos.local",
            salt=salt,
            hash_pwd=pwd_hash
        )
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "test_user_1")
        self.assertEqual(user["name"], "Test User 1")

        # 1. Lookup by username (case-insensitive)
        by_user = get_user_by_login("TEST_USER_1")
        self.assertIsNotNone(by_user)
        self.assertEqual(by_user["id"], user["id"])

        # 2. Lookup by email (case-insensitive)
        by_email = get_user_by_login("TEST_USER_1@ARGOS.LOCAL")
        self.assertIsNotNone(by_email)
        self.assertEqual(by_email["id"], user["id"])

        # 3. Lookup by name and org
        by_name_org = get_user_by_login("Test User 1", org="dev")
        self.assertIsNotNone(by_name_org)
        self.assertEqual(by_name_org["id"], user["id"])

    def test_duplicate_username_rejected(self):
        salt, pwd_hash = hash_password("Password123!")
        create_user(
            name="Test User A",
            username="test_dup_user",
            org="dev",
            email="test_a@argos.local",
            salt=salt,
            hash_pwd=pwd_hash
        )

        # Same username with different casing
        with self.assertRaises(ValueError) as ctx:
            create_user(
                name="Test User B",
                username="TEST_DUP_USER",
                org="sales",
                email="test_b@argos.local",
                salt=salt,
                hash_pwd=pwd_hash
            )
        self.assertIn("ArgosWorks ID", str(ctx.exception))

    def test_duplicate_email_rejected(self):
        salt, pwd_hash = hash_password("Password123!")
        create_user(
            name="Test User C",
            username="test_user_c",
            org="dev",
            email="common_email@argos.local",
            salt=salt,
            hash_pwd=pwd_hash
        )

        with self.assertRaises(ValueError) as ctx:
            create_user(
                name="Test User D",
                username="test_user_d",
                org="dev",
                email="COMMON_EMAIL@ARGOS.LOCAL",
                salt=salt,
                hash_pwd=pwd_hash
            )
        self.assertIn("이메일", str(ctx.exception))

    def test_safe_delete_user_nullifies_fk_and_prevents_orphans(self):
        salt, pwd_hash = hash_password("Password123!")
        user = create_user(
            name="Test Assignee",
            username="test_assignee",
            org="dev",
            email="test_assignee@argos.local",
            salt=salt,
            hash_pwd=pwd_hash
        )
        uid = user["id"]

        # Insert a task assigned to this user (FK: assignee_id)
        execute(
            """INSERT INTO records(id, dept_id, category, title, assignee_id, assignee_name, assignee_email, status)
               VALUES (999001, 'dev', 'General', 'test_task_1', ?, 'Test Assignee', 'test_assignee@argos.local', '진행')""",
            (uid,)
        )

        # Insert a schedule event owned by this user (FK: owner_id)
        execute(
            """INSERT INTO schedule_events(id, owner_id, owner_name, owner_dept_id, type, title, start_date, end_date)
               VALUES (999002, ?, 'Test Assignee', 'dev', 'Task', 'test_event_1', '2026-10-21', '2026-10-22')""",
            (uid,)
        )

        # Safely delete user
        ok = safe_delete_user(uid)
        self.assertTrue(ok)

        # User is deleted
        deleted_user = get_user_by_id(uid)
        self.assertIsNone(deleted_user)

        # FK in records is NULLIFIED (no orphaned FK, no FK constraint crash)
        rec = get_one("SELECT * FROM records WHERE id = 999001")
        self.assertIsNotNone(rec)
        self.assertIsNone(rec["assignee_id"])

        # FK in schedule_events is NULLIFIED
        ev = get_one("SELECT * FROM schedule_events WHERE id = 999002")
        self.assertIsNotNone(ev)
        self.assertIsNone(ev["owner_id"])

    def test_concurrent_user_registration(self):
        # Simulate 20 concurrent threads attempting to register unique and duplicate users
        errors = []
        registered_uids = []
        salt, pwd_hash = hash_password("Pass12345!")

        def worker(idx):
            username = f"test_worker_{idx}"
            email = f"test_worker_{idx}@argos.local"
            name = f"Test Worker {idx}"
            try:
                u = create_user(
                    name=name,
                    username=username,
                    org="dev",
                    email=email,
                    salt=salt,
                    hash_pwd=pwd_hash
                )
                if u:
                    registered_uids.append(u["id"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 20 workers succeeded without overwriting or deleting each other
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(registered_uids), 20)
        self.assertEqual(len(set(registered_uids)), 20)

    def test_nested_transactions_success(self):
        from db import transaction
        salt, pwd_hash = hash_password("Pass12345!")

        def outer(conn):
            create_user(
                name="Test Outer User",
                username="test_outer_u",
                org="dev",
                email="outer@argos.local",
                salt=salt,
                hash_pwd=pwd_hash
            )
            def inner(conn2):
                create_user(
                    name="Test Inner User",
                    username="test_inner_u",
                    org="dev",
                    email="inner@argos.local",
                    salt=salt,
                    hash_pwd=pwd_hash
                )
            transaction(inner)

        transaction(outer)

        self.assertIsNotNone(get_user_by_login("test_outer_u"))
        self.assertIsNotNone(get_user_by_login("test_inner_u"))

    def test_nested_transaction_partial_rollback(self):
        from db import transaction
        salt, pwd_hash = hash_password("Pass12345!")

        def outer(conn):
            create_user(
                name="Test Main User",
                username="test_main_u",
                org="dev",
                email="main@argos.local",
                salt=salt,
                hash_pwd=pwd_hash
            )
            try:
                def failing_inner(conn2):
                    create_user(
                        name="Test Failed User",
                        username="test_fail_u",
                        org="dev",
                        email="fail@argos.local",
                        salt=salt,
                        hash_pwd=pwd_hash
                    )
                    raise RuntimeError("Intentional nested failure")
                transaction(failing_inner)
            except RuntimeError:
                pass  # Catch error, outer transaction continues

        transaction(outer)

        # Outer succeeded
        self.assertIsNotNone(get_user_by_login("test_main_u"))
        # Inner rolled back cleanly via SAVEPOINT
        self.assertIsNone(get_user_by_login("test_fail_u"))


if __name__ == "__main__":
    unittest.main()
