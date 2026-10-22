"""
Regression tests for client-IP resolution behind a reverse proxy (P0).

Background: `_extract_client_ip()` trusted X-Forwarded-For whenever the TCP peer
was *any* private address (10/8, 172.16/12, 192.168/16) and returned the
left-most header value. On a LAN install (`python server/main.py`, no proxy) any
workstation could therefore spoof its IP, bypassing the per-IP rate limiter and
poisoning the IP recorded in the audit log.

New contract:
  * headers are read only when the direct peer matches TRUSTED_PROXIES;
  * the chain is walked right-to-left, so client-supplied prefixes are ignored;
  * malformed values never become the resolved IP.
"""
import os
import sys
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from handler import (  # noqa: E402
    DEFAULT_TRUSTED_PROXIES,
    ArgosHandler,
    is_trusted_proxy_peer,
)


class FakeRequest(ArgosHandler):
    """ArgosHandler without the socket: only client_address + headers are used."""

    def __init__(self, peer, headers=None):
        self.client_address = (peer, 40123)
        self.headers = headers or {}

    def address_string(self):
        return self.client_address[0]


def resolve(peer, **headers):
    return FakeRequest(peer, headers)._extract_client_ip()


class TestTrustedProxyConfiguration(unittest.TestCase):
    def test_defaults_cover_loopback_and_docker_bridge(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRUSTED_PROXIES", None)
            self.assertEqual(DEFAULT_TRUSTED_PROXIES, "127.0.0.1,::1,172.16.0.0/12")
            self.assertTrue(is_trusted_proxy_peer("127.0.0.1"))
            self.assertTrue(is_trusted_proxy_peer("::1"))
            self.assertTrue(is_trusted_proxy_peer("172.17.0.2"))
            self.assertFalse(is_trusted_proxy_peer("192.168.1.50"))
            self.assertFalse(is_trusted_proxy_peer("10.1.2.3"))

    def test_explicit_cidr_is_honoured(self):
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "127.0.0.1,10.0.5.0/24"}):
            self.assertTrue(is_trusted_proxy_peer("10.0.5.9"))
            self.assertFalse(is_trusted_proxy_peer("172.17.0.2"))

    def test_wildcard_is_opt_in_only(self):
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "0.0.0.0"}):
            self.assertTrue(is_trusted_proxy_peer("203.0.113.9"))


class TestClientIpResolution(unittest.TestCase):
    def test_direct_client_cannot_spoof_forwarded_header(self):
        """No proxy in front: the header must be ignored entirely."""
        self.assertEqual(
            resolve("203.0.113.9", **{"X-Forwarded-For": "1.1.1.1"}),
            "203.0.113.9",
        )

    def test_lan_peer_cannot_spoof_forwarded_header(self):
        """LAN workstation (192.168/16) is not a trusted proxy any more."""
        self.assertEqual(
            resolve("192.168.1.50", **{"X-Forwarded-For": "10.9.9.9"}),
            "192.168.1.50",
        )

    def test_trusted_proxy_header_is_used(self):
        self.assertEqual(
            resolve("127.0.0.1", **{"X-Forwarded-For": "198.51.100.7"}),
            "198.51.100.7",
        )

    def test_docker_proxy_header_is_used(self):
        self.assertEqual(
            resolve("172.17.0.2", **{"X-Forwarded-For": "203.0.113.9, 172.17.0.2"}),
            "203.0.113.9",
        )

    def test_client_supplied_prefix_is_ignored(self):
        """Caddy appends the real peer, so the right-most untrusted hop wins."""
        self.assertEqual(
            resolve("172.17.0.2", **{"X-Forwarded-For": "1.2.3.4, 203.0.113.50"}),
            "203.0.113.50",
        )

    def test_x_real_ip_is_used_when_forwarded_for_absent(self):
        self.assertEqual(
            resolve("172.17.0.2", **{"X-Real-IP": "198.51.100.42"}),
            "198.51.100.42",
        )

    def test_malformed_header_values_fall_back_to_peer(self):
        self.assertEqual(
            resolve("172.17.0.2", **{"X-Forwarded-For": "not-an-ip, <script>"}),
            "172.17.0.2",
        )

    def test_ipv6_loopback_proxy_is_supported(self):
        self.assertEqual(
            resolve("::1", **{"X-Forwarded-For": "2001:db8::1"}),
            "2001:db8::1",
        )


if __name__ == "__main__":
    unittest.main()
