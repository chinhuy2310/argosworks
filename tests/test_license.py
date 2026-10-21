import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from services.license_manager import generate_signed_license_key, get_license_secret

class TestLicenseManager(unittest.TestCase):
    def setUp(self):
        os.environ["ARGOS_LICENSE_SECRET"] = "TEST_SECRET_KEY_FOR_UNIT_TESTING_12345"

    def test_signed_license_key_generation(self):
        key = generate_signed_license_key(
            customer_name="Test Enterprise Inc.",
            max_seats=50,
            expiry_date_str="2027-12-31",
            modules=["canvas", "jira", "rag"]
        )
        self.assertTrue(key.startswith("AGY-"))
        self.assertIn(".", key)

    def test_missing_secret_detection(self):
        old_val = os.environ.pop("ARGOS_LICENSE_SECRET", None)
        old_master = os.environ.pop("JARVIS_MASTER_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                get_license_secret()
        finally:
            if old_val:
                os.environ["ARGOS_LICENSE_SECRET"] = old_val
            if old_master:
                os.environ["JARVIS_MASTER_KEY"] = old_master

if __name__ == "__main__":
    unittest.main()
