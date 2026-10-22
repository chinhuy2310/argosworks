import json
import os
import mimetypes
import tempfile
import traceback
import urllib.parse
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from services.auth import get_session
from router import match_get, match_post
from utils.logging import log_line, access_log
from middleware_security import check_rate_limit, validate_csrf_token, get_allowed_cors_origin
from db import close_connection

PUBLIC_API_WHITELIST = {
    # System health & Setup
    "/api/health",
    "/api/setup/status",
    "/api/setup/verify-license",
    "/api/setup/complete",

    # Authentication & Session Handshake
    "/api/account/check",
    "/api/auth/check",
    "/api/account/login",
    "/api/auth/login",
    "/api/account/register",
    "/api/auth/register",
    "/api/account/csrf",
    "/api/auth/csrf",
    "/api/account/logout",
    "/api/auth/logout",
    "/api/account/logout-all",
    "/api/auth/logout-all",
    "/api/account/me",

    # Public Workspace UI Branding
    "/api/workspace-config",
}

class ArgosHandler(BaseHTTPRequestHandler):
    server_version = "ArgosServer/2.0"
    cfg = None  # class-level, set in main()
    timeout = 60  # Socket inactivity timeout (seconds) preventing thread leaks

    def log_message(self, fmt, *args):
        log_line(self.address_string(), fmt % args)

    # ---- 공통 응답 헬퍼 ----
    def _send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Enterprise Hardened Headers (Zero-Day & Injection Prevention)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Server", "ArgosEnterprise/2.0")
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _is_secure(self):
        """요청이 HTTPS를 통해 전달되었는지 검사 (Direct TLS 또는 Reverse Proxy X-Forwarded-Proto)."""
        proto = (self.headers.get("X-Forwarded-Proto") or "").lower()
        if proto == "https":
            return True
        if hasattr(self.connection, "getpeercert"):
            return True
        return False

    def _make_auth_cookie_header(self, token, max_age_days=1):
        """Enterprise HttpOnly Cookie 헤더 생성 (SameSite=Lax, HttpOnly, HTTPS 시 Secure 플래그 적용, 기본 24h)."""
        max_age = int(max_age_days * 24 * 3600)
        cookie = f"argos_token={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
        if self._is_secure():
            cookie += "; Secure"
        return ("Set-Cookie", cookie)

    def _make_logout_cookie_header(self):
        """세션 만료용 Set-Cookie 헤더 생성."""
        cookie = "argos_token=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
        if self._is_secure():
            cookie += "; Secure"
        return ("Set-Cookie", cookie)

    def _extract_client_ip(self):
        """
        Extract real client IP considering trusted reverse proxy headers (X-Forwarded-For).
        Only trusts X-Forwarded-For / X-Real-IP if direct connection peer is in TRUSTED_PROXIES.
        """
        peer_ip = ""
        try:
            peer_ip = self.client_address[0]
        except Exception:
            peer_ip = self.address_string()

        # Defaults trust local connections as well as Docker bridge/container networks (caddy reverse proxy)
        trusted_proxies_cfg = os.environ.get("TRUSTED_PROXIES", "127.0.0.1,::1,localhost,caddy,argos-proxy")
        trusted_proxies = {p.strip() for p in trusted_proxies_cfg.split(",") if p.strip()}

        # Check if direct peer IP or peer hostname matches trusted proxies or Docker private subnet (172.16.0.0/12)
        is_trusted = (peer_ip in trusted_proxies or "0.0.0.0" in trusted_proxies)
        if not is_trusted:
            try:
                import ipaddress
                ip_obj = ipaddress.ip_address(peer_ip)
                # Docker internal networks are private IPs (172.16.0.0 - 172.31.255.255, 10.0.0.0/8, 192.168.0.0/16)
                if ip_obj.is_private:
                    is_trusted = True
            except Exception:
                pass

        if is_trusted:
            xff = self.headers.get("X-Forwarded-For")
            if xff:
                parts = [p.strip() for p in xff.split(",")]
                if parts and parts[0]:
                    return parts[0]
            real_ip = self.headers.get("X-Real-IP")
            if real_ip and real_ip.strip():
                return real_ip.strip()

        return peer_ip

    def _extract_token(self):
        """
        인증 토큰을 안전하게 추출한다.
        1. Cookie 헤더 (argos_token=<token>) - XSS / F12 방어형 HttpOnly
        2. Authorization: Bearer <token> - 하위 호환성 및 API 클라이언트 지원
        * 보안 강화: Query string (?token=...) 전송은 전면 차단 (URL 로깅 및 어깨 너머 노출 방지).
        """
        # 1. Cookie 우선 검사
        cookie_header = self.headers.get("Cookie", "") or ""
        if "argos_token=" in cookie_header:
            from http.cookies import SimpleCookie
            try:
                sc = SimpleCookie()
                sc.load(cookie_header)
                if "argos_token" in sc and sc["argos_token"].value:
                    return sc["argos_token"].value.strip()
            except Exception:
                pass

        # 2. Authorization 헤더 Fallback
        auth = self.headers.get("Authorization", "") or ""
        if auth.startswith("Bearer "):
            return auth[7:].strip()

        return ""

    def _get_session_or_401(self):
        if hasattr(self, "_current_session") and self._current_session:
            return self._current_session
        token = self._extract_token()
        session = get_session(token) if token else None
        self._current_session = session
        if not session:
            self._send_json(401, {"ok": False, "error": "로그인이 필요합니다.", "authRequired": True})
            return None
        return session

    def _get_session_optional(self):
        """로그인 여부가 필수는 아니지만, 로그인돼 있으면 그 정보를 쓰고 싶은 곳에서
        사용한다(예: /api/ask에서 본인 캘린더까지 검색 범위에 포함시킬지 여부).
        토큰이 없거나 유효하지 않아도 401을 보내지 않고 조용히 None을 돌려준다."""
        if hasattr(self, "_current_session") and self._current_session is not None:
            return self._current_session
        token = self._extract_token()
        session = get_session(token) if token else None
        self._current_session = session
        return session

    def _send_file(self, path, content_type):
        try:
            stat = os.stat(path)
            # Tạo ETag dựa trên mtime và size của file
            etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
            
            # Kiểm tra If-None-Match từ client để trả về 304 Not Modified
            if_none_match = self.headers.get("If-None-Match")
            if if_none_match and if_none_match.strip() == etag:
                self.send_response(304)
                self.end_headers()
                return

            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)

        # File tĩnh (css, js, assets, images) cho cache 1 ngày để tăng tốc độ tải mạng LAN
        is_static_asset = any(p in path.replace("\\", "/") for p in ["/css/", "/js/", "/assets/", "/images/", "favicon.svg"])
        if is_static_asset:
            self.send_header("Cache-Control", "public, max-age=86400")
        else:
            self.send_header("Cache-Control", "no-cache")

        self.end_headers()
        self.wfile.write(body)

    def _send_attachment(self, path, download_name):
        """첨부파일을 '다운로드'로 내려준다(Content-Disposition: attachment) —
        _send_file은 화면 리소스(index.html 등)를 그대로 표시하는 용도라 이것과 다르다."""
        try:
            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        content_type, _ = mimetypes.guess_type(download_name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition",
                          "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "sandbox")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _start_sse(self):
        """SSE(Server-Sent Events) 스트리밍 응답을 시작한다."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()

    def _send_sse_event(self, data):
        """하나의 SSE 이벤트를 전송한다. 클라이언트 접속 종료 시 False 반환."""
        try:
            payload = json.dumps(data, ensure_ascii=False)
            self.wfile.write(f"data: {payload}\n\n".encode('utf-8'))
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return False

    def _end_sse(self):
        """SSE 스트림을 종료한다."""
        try:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    # ---- OPTIONS (CORS Preflight) ----
    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        allowed_domain = self.headers.get("Host", "localhost")
        self.send_response(204)
        if origin:
            from middleware_security import get_allowed_cors_origin
            allowed = get_allowed_cors_origin(origin, [allowed_domain])
            if allowed:
                self.send_header("Access-Control-Allow-Origin", allowed)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-CSRF-Token")
                self.send_header("Access-Control-Allow-Credentials", "true")
                self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    # ---- HEAD ----
    def do_HEAD(self):
        self.do_GET()

    # ---- GET ----
    def do_GET(self):
        try:
            parsed = urlsplit(self.path)
            path = parsed.path
            ip = self._extract_client_ip()

            # Enterprise Rate Limiting Check (bypass static files for smooth UX)
            if path.startswith("/api/"):
                allowed, retry_after = check_rate_limit(ip, limit_rpm=180)
                if not allowed:
                    self._send_json(429, {"ok": False, "error": f"요청 한도(Rate limit)를 초과했습니다. {retry_after}초 후 다시 시도하세요."}, extra_headers=[("Retry-After", str(retry_after))])
                    return

                # Default Authentication Guard: all /api endpoints require login unless whitelisted
                if path not in PUBLIC_API_WHITELIST:
                    if not self._get_session_or_401():
                        return

            try:
                route_type, handler_or_path, content_type = match_get(path)
                
                if route_type == "file":
                    self._send_file(handler_or_path, content_type)
                elif route_type == "redirect":
                    self.send_response(302)
                    self.send_header("Location", handler_or_path)
                    self.end_headers()
                elif route_type == "nocontent":
                    self.send_response(204)
                    self.end_headers()
                elif route_type == "handler":
                    handler_or_path(self, parsed, ip)
                elif route_type == "notfound":
                    self._send_json(404, {"ok": False, "error": "not found"})
                    
            except Exception as e:
                import traceback
                log_line("GET 처리 중 오류:\n", traceback.format_exc())
                self._send_json(500, {"ok": False, "error": "서버 내부 오류가 발생했습니다. (Internal Server Error)"})
        finally:
            close_connection()

    # ---- POST ----
    def do_POST(self):
        try:
            parsed = urlsplit(self.path)
            path = parsed.path
            ip = self._extract_client_ip()

            # Enterprise Rate Limiting Check on API mutations
            if path.startswith("/api/"):
                allowed, retry_after = check_rate_limit(ip, limit_rpm=120)
                if not allowed:
                    self._send_json(429, {"ok": False, "error": f"요청 한도(Rate limit)를 초과했습니다. {retry_after}초 후 다시 시도하세요."}, extra_headers=[("Retry-After", str(retry_after))])
                    return

                # Default Authentication Guard: all /api endpoints require login unless whitelisted
                if path not in PUBLIC_API_WHITELIST:
                    if not self._get_session_or_401():
                        return

                # CSRF Protection for state-changing endpoints (exempt whitelisted public endpoints)
                if path not in PUBLIC_API_WHITELIST:
                    csrf_header = self.headers.get("X-CSRF-Token", "")
                    session_token = self._extract_token()
                    # If request has session cookie, validate CSRF token to prevent cross-site request forgery
                    cookie_header = self.headers.get("Cookie", "")
                    if "argos_token=" in cookie_header:
                        valid_csrf = validate_csrf_token(csrf_header, session_token=session_token)
                        
                        # Fallback A: Double-submit cookie (argos_csrf)
                        if not valid_csrf:
                            try:
                                sc = SimpleCookie()
                                sc.load(cookie_header)
                                if "argos_csrf" in sc and sc["argos_csrf"].value:
                                    valid_csrf = validate_csrf_token(sc["argos_csrf"].value, session_token=session_token)
                            except Exception:
                                pass

                        # Fallback B: Browser Same-Origin Verification (Sec-Fetch-Site / Origin / Referer against Host)
                        if not valid_csrf:
                            sec_fetch_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
                            origin = (self.headers.get("Origin") or "").strip().lower()
                            host = (self.headers.get("Host") or "").strip().lower()
                            referer = (self.headers.get("Referer") or "").strip().lower()

                            origin_match = False
                            if origin:
                                try:
                                    origin_match = (urlsplit(origin).netloc.lower() == host)
                                except Exception:
                                    pass
                            elif referer:
                                try:
                                    origin_match = (urlsplit(referer).netloc.lower() == host)
                                except Exception:
                                    pass

                            # If guaranteed same-origin by browser security boundary
                            if sec_fetch_site == "same-origin" or origin_match:
                                valid_csrf = True

                        if not valid_csrf:
                            self._send_json(403, {"ok": False, "error": "CSRF 검증 실패 (Invalid or missing CSRF token)"})
                            return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                max_bytes = int((self.cfg.get("max_upload_mb", 25))) * 1024 * 1024
                if length > max_bytes:
                    self._send_json(413, {"ok": False, "error": "업로드 용량 제한(%dMB) 초과" % self.cfg.get("max_upload_mb", 25)})
                    return
                # Stream read body with memory capping (prevents thread OOM during concurrent uploads)
                # Small payloads (<1MB) stay in memory, large payloads spill safely to temporary disk
                import tempfile
                raw_body = b""
                if length > 0:
                    if length <= 1024 * 1024:
                        raw_body = self.rfile.read(length)
                    else:
                        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as spool:
                            remaining = length
                            chunk_size = 64 * 1024
                            while remaining > 0:
                                chunk = self.rfile.read(min(remaining, chunk_size))
                                if not chunk:
                                    break
                                spool.write(chunk)
                                remaining -= len(chunk)
                            spool.seek(0)
                            raw_body = spool.read()

                handler_func = match_post(path)
                if handler_func:
                    handler_func(self, raw_body, ip)
                else:
                    self._send_json(404, {"ok": False, "error": "not found"})
            except Exception as e:
                import traceback
                log_line("POST 처리 중 오류:\n", traceback.format_exc())
                access_log(ip, "error", 500, f"Exception: {type(e).__name__}")
                self._send_json(500, {"ok": False, "error": "서버 내부 오류가 발생했습니다. (Internal Server Error)"})
        finally:
            close_connection()

# Backward compatibility alias
JarvisHandler = ArgosHandler
