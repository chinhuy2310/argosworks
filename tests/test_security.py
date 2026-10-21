import os
import sys
import unittest
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from middleware_security import check_rate_limit, generate_csrf_token, validate_csrf_token, get_allowed_cors_origin

class TestSecurityMiddleware(unittest.TestCase):
    def test_rate_limiter_allows_under_limit(self):
        ip = "192.168.1.100"
        allowed, retry_after = check_rate_limit(ip, limit_rpm=10)
        self.assertTrue(allowed)
        self.assertEqual(retry_after, 0)

    def test_rate_limiter_blocks_over_limit(self):
        ip = "192.168.1.200"
        for _ in range(5):
            check_rate_limit(ip, limit_rpm=5)
        
        # 6th request must be rejected
        allowed, retry_after = check_rate_limit(ip, limit_rpm=5)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_csrf_token_lifecycle(self):
        token = generate_csrf_token("test-session-token-123")
        self.assertTrue(validate_csrf_token(token))
        self.assertFalse(validate_csrf_token("invalid-tampered-token"))

    def test_strict_cors_origin_whitelist(self):
        whitelist = ["company.com", "argos.internal"]
        
        # Exact domain match
        self.assertIsNotNone(get_allowed_cors_origin("https://company.com", whitelist))
        # Subdomain match
        self.assertIsNotNone(get_allowed_cors_origin("https://sub.company.com", whitelist))
        # Malicious external origin blocked
        self.assertIsNone(get_allowed_cors_origin("https://evil-hacker.com", whitelist))
        self.assertIsNone(get_allowed_cors_origin(None, whitelist))

if __name__ == "__main__":
    unittest.main()
