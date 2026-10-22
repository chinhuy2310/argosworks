import os
import sys
import unittest
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from db import init_db
from services.license_manager import (
    generate_signed_license_key,
    verify_license_key,
    activate_license,
    get_license_status,
    check_seat_available,
    is_system_read_only,
)

class TestLicenseManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_signed_license_key_generation_and_verification(self):
        exp = (date.today() + timedelta(days=365)).strftime("%Y-%m-%d")
        key = generate_signed_license_key(
            customer_name="Test Enterprise Inc.",
            max_seats=50,
            expiry_date_str=exp,
            modules=["canvas", "jira", "rag"]
        )
        self.assertTrue(key.startswith("AGY-"))
        self.assertIn(".", key)

        # Verify valid key
        ok, msg, data = verify_license_key(key)
        self.assertTrue(ok, msg)
        self.assertEqual(data["customer"], "Test Enterprise Inc.")
        self.assertEqual(data["seats"], 50)
        self.assertEqual(data["expiry"], exp)
        self.assertIn("canvas", data["modules"])

    def test_tampered_license_key_rejection(self):
        exp = (date.today() + timedelta(days=365)).strftime("%Y-%m-%d")
        key = generate_signed_license_key(
            customer_name="Test Enterprise Inc.",
            max_seats=50,
            expiry_date_str=exp,
            modules=["canvas"]
        )
        # Tamper payload
        parts = key.split(".")
        tampered = parts[0][:-2] + "AA." + parts[1]
        ok, msg, data = verify_license_key(tampered)
        self.assertFalse(ok)

    def test_expired_license_key_rejection(self):
        expired_date = "2020-01-01"
        key = generate_signed_license_key(
            customer_name="Expired Org",
            max_seats=10,
            expiry_date_str=expired_date,
            modules=["canvas"]
        )
        ok, msg, data = verify_license_key(key)
        self.assertFalse(ok)
        self.assertIn("만료", msg)

    def test_activate_license_and_status(self):
        exp = (date.today() + timedelta(days=100)).strftime("%Y-%m-%d")
        key = generate_signed_license_key(
            customer_name="Active Corp",
            max_seats=15,
            expiry_date_str=exp,
            modules=["canvas", "jira", "pim"]
        )
        ok, msg = activate_license(key)
        self.assertTrue(ok, msg)

        status = get_license_status()
        self.assertEqual(status["customer_name"], "Active Corp")
        self.assertEqual(status["max_seats"], 15)
        self.assertFalse(status["is_expired"])
        self.assertFalse(status["is_read_only"])
        self.assertFalse(is_system_read_only())

if __name__ == "__main__":
    unittest.main()
