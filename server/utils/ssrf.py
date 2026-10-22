import socket
import ipaddress
import urllib.parse
from typing import Optional

def validate_external_url(url: str, allow_private: bool = False, require_https: bool = True) -> bool:
    """
    SSRF (Server-Side Request Forgery) 방어용 엄격한 URL 검증기:
    1. Scheme 검사: 기본적으로 https:// 만 허용 (Ollama 등 로컬 AI 허용 옵션일 때만 http:// 허용).
    2. DNS 해석을 통한 실제 대상 IP 주소 검사:
       - Loopback (127.0.0.0/8, ::1)
       - Link-local (169.254.0.0/16, fe80::/10) — AWS/GCP/Azure 클라우드 메타데이터 169.254.169.254 차단
       - Private IP (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7)
       - Multicast, Reserved, Unspecified (0.0.0.0)
    위험 IP 발견 시 즉시 ValueError를 발생시켜 외부 요청을 사전 차단한다.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL이 입력되지 않았습니다.")

    url_clean = url.strip()
    parsed = urllib.parse.urlsplit(url_clean)
    scheme = (parsed.scheme or "").lower()

    if require_https and not allow_private:
        if scheme != "https":
            raise ValueError(f"보안 위험: HTTPS 프로토콜만 허용됩니다 ({scheme}:// 불허)")
    else:
        if scheme not in ("http", "https"):
            raise ValueError(f"보안 위험: HTTP 또는 HTTPS 프로토콜만 지원됩니다 ({scheme}:// 불허)")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("유효하지 않은 호스트명입니다.")

    port = parsed.port or (443 if scheme == "https" else 80)

    # DNS 해석 및 IP 대역 검증
    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"호스트명을 확인할 수 없습니다 ({hostname}): {e}")

    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        # 1. Link-local (169.254.x.x Cloud Metadata) — 무조건 차단 (내부망 허용 옵션과 무관)
        if ip.is_link_local:
            raise ValueError(f"SSRF 보안 위험: Link-local 및 클라우드 메타데이터 IP({ip}) 접근이 차단되었습니다.")

        # 2. Loopback (127.0.0.1, ::1)
        if ip.is_loopback and not allow_private:
            raise ValueError(f"SSRF 보안 위험: 루프백 IP({ip}) 접근이 차단되었습니다.")

        # 3. Private IP ranges (10.x, 172.16-31.x, 192.168.x)
        if ip.is_private and not allow_private:
            raise ValueError(f"SSRF 보안 위험: 사설망 IP({ip}) 접근이 차단되었습니다.")

        # 4. Multicast, Reserved, Unspecified
        if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError(f"SSRF 보안 위험: 특수 목적 IP({ip}) 접근이 차단되었습니다.")

    return True
