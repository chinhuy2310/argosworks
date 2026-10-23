"""
Unit & Integration Tests for ARGOS WORKS WSGI Production Interface.
Tests PEP 3333 compliance, security headers, routing, static assets, and auth guards.
"""
import os
import sys
import io
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from wsgi import application, ArgosWSGIHandler, _decode_wsgi_path
from config import load_config
from handler import ArgosHandler
from services.auth import create_session, get_user_by_login


class WSGITestClient:
    """Lightweight test client for invoking WSGI application directly."""
    def __init__(self, app):
        self.app = app

    def request(self, method, path, body=b"", headers=None, remote_addr="127.0.0.1"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        elif isinstance(body, dict):
            body = json.dumps(body).encode("utf-8")

        query_string = ""
        if "?" in path:
            path, query_string = path.split("?", 1)

        environ = {
            "REQUEST_METHOD": method.upper(),
            "PATH_INFO": path,
            "QUERY_STRING": query_string,
            "REMOTE_ADDR": remote_addr,
            "REMOTE_PORT": "54321",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }

        if body:
            environ["CONTENT_LENGTH"] = str(len(body))

        if headers:
            for k, v in headers.items():
                if k.lower() == "content-type":
                    environ["CONTENT_TYPE"] = str(v)
                elif k.lower() == "content-length":
                    environ["CONTENT_LENGTH"] = str(v)
                else:
                    env_k = "HTTP_" + k.upper().replace("-", "_")
                    environ[env_k] = str(v)

        recorded = {"status": None, "headers": [], "body": []}

        def start_response(status, response_headers, exc_info=None):
            recorded["status"] = status
            recorded["headers"] = response_headers
            return recorded["body"].append

        result_iter = self.app(environ, start_response)
        for chunk in result_iter:
            recorded["body"].append(chunk)

        status_code = int(recorded["status"].split()[0]) if recorded["status"] else 500
        headers_dict = {}
        for k, v in recorded["headers"]:
            headers_dict[k.lower()] = v

        full_body = b"".join(recorded["body"])
        json_data = None
        try:
            json_data = json.loads(full_body.decode("utf-8"))
        except Exception:
            pass

        return {
            "status_code": status_code,
            "status": recorded["status"],
            "headers": recorded["headers"],
            "headers_dict": headers_dict,
            "body": full_body,
            "json": json_data,
        }

    def get(self, path, headers=None):
        return self.request("GET", path, headers=headers)

    def post(self, path, body=b"", headers=None):
        return self.request("POST", path, body=body, headers=headers)

    def options(self, path, headers=None):
        return self.request("OPTIONS", path, headers=headers)


class TestWSGIProduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = WSGITestClient(application)
        cfg = load_config()
        ArgosHandler.cfg = cfg

    def test_health_check_endpoint(self):
        """GET /api/health should return 200 OK with healthy JSON payload."""
        res = self.client.get("/api/health")
        self.assertEqual(res["status_code"], 200)
        self.assertIsNotNone(res["json"])
        self.assertTrue(res["json"].get("ok"))
        self.assertEqual(res["json"].get("status"), "healthy")
        self.assertEqual(res["headers_dict"].get("content-type"), "application/json; charset=utf-8")
        self.assertEqual(res["headers_dict"].get("x-content-type-options"), "nosniff")

    def test_static_index_html(self):
        """GET / should serve the SPA index.html with appropriate enterprise security headers."""
        import handlers.setup_handler as setup_handler
        old_cache = setup_handler._setup_completed_cache
        setup_handler._setup_completed_cache = True
        try:
            res = self.client.get("/")
            self.assertEqual(res["status_code"], 200)
            self.assertIn(b"ARGOS WORKS", res["body"])
            self.assertEqual(res["headers_dict"].get("x-frame-options"), "SAMEORIGIN")
            self.assertEqual(res["headers_dict"].get("x-content-type-options"), "nosniff")
        finally:
            setup_handler._setup_completed_cache = old_cache

    def test_no_hop_by_hop_headers(self):
        """PEP 3333 prohibits hop-by-hop headers in WSGI application responses."""
        res = self.client.get("/api/health")
        forbidden = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}
        for k, v in res["headers"]:
            self.assertNotIn(k.lower(), forbidden, f"Forbidden hop-by-hop header found: {k}")

    def test_auth_guard_on_protected_endpoints(self):
        """Unauthenticated requests to protected API endpoints must return 401."""
        res = self.client.get("/api/departments")
        self.assertEqual(res["status_code"], 401)
        self.assertIsNotNone(res["json"])
        self.assertFalse(res["json"].get("ok"))
        self.assertTrue(res["json"].get("authRequired"))

    def test_authenticated_request_succeeds(self):
        """Authenticated requests with valid session cookie should return 200."""
        user = get_user_by_login("admin")
        if not user:
            # Fallback to test user or skip
            self.skipTest("Admin user not found")
        token = create_session(user["id"])
        headers = {
            "Cookie": f"argos_token={token}",
        }
        res = self.client.get("/api/departments", headers=headers)
        self.assertEqual(res["status_code"], 200)
        self.assertIsNotNone(res["json"])
        self.assertTrue(res["json"].get("ok"))
        self.assertIn("departments", res["json"])

    def test_cors_preflight_options(self):
        """OPTIONS /api/health should return 204 No Content with CORS headers."""
        headers = {
            "Origin": "http://localhost:8080",
            "Host": "localhost:8080",
            "Access-Control-Request-Method": "POST",
        }
        res = self.client.options("/api/health", headers=headers)
        self.assertEqual(res["status_code"], 204)
        self.assertIn("access-control-allow-origin", res["headers_dict"])
        """OPTIONS /api/health should return 204 No Content with CORS headers."""
        headers = {
            "Origin": "http://localhost:8080",
            "Host": "localhost:8080",
            "Access-Control-Request-Method": "POST",
        }
        res = self.client.options("/api/health", headers=headers)
        self.assertEqual(res["status_code"], 204)
        self.assertIn("access-control-allow-origin", res["headers_dict"])

    def test_unicode_path_decoding(self):
        """WSGI latin-1 encoded paths should decode to valid UTF-8 strings."""
        raw_encoded = "/api/files/test.pdf"
        self.assertEqual(_decode_wsgi_path(raw_encoded), "/api/files/test.pdf")

        # Emulate latin-1 string containing UTF-8 bytes for Korean
        utf8_bytes = "테스트".encode("utf-8")
        latin1_str = utf8_bytes.decode("latin-1")
        decoded = _decode_wsgi_path(f"/api/files/{latin1_str}.pdf")
        self.assertEqual(decoded, "/api/files/테스트.pdf")


if __name__ == "__main__":
    unittest.main()
