import os
import sys
import unittest
import tempfile
import shutil

# Add server directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from utils.crypto import encrypt_secret, decrypt_secret, is_encrypted, get_master_key

class TestCrypto(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        plain = "super-secret-jira-api-token-2026!@#$%^"
        enc = encrypt_secret(plain)
        self.assertTrue(is_encrypted(enc))
        self.assertNotEqual(plain, enc)
        
        dec = decrypt_secret(enc)
        self.assertEqual(plain, dec)

    def test_empty_and_plain_passthrough(self):
        self.assertEqual(encrypt_secret(""), "")
        self.assertEqual(decrypt_secret("plain_text_without_prefix"), "plain_text_without_prefix")

    def test_tamper_detection(self):
        plain = "test-sensitive-value"
        enc = encrypt_secret(plain)
        # Modify ciphertext payload slightly
        tampered = enc[:-4] + "AAAA"
        dec = decrypt_secret(tampered)
        self.assertEqual(dec, "")  # HMAC verification fails

if __name__ == "__main__":
    unittest.main()
