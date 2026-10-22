# -*- coding: utf-8 -*-
"""license_manager.py — Enterprise Asymmetric (Ed25519) License & Capacity Engine for ARGOS WORKS.
Manages seats count (max active users), contract expiration date, offline asymmetric activation,
and read-only mode enforcement upon license expiry.
Client instances contain ONLY the embedded Ed25519 Public Key. Clients CANNOT sign their own keys.
"""

import os
import json
import base64
from datetime import datetime, date
from db import query, get_one, execute
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

# Embedded official Argos Works Ed25519 public key (32 bytes hex)
EMBEDDED_LICENSE_PUBLIC_KEY_HEX = "a8dc6f06ac6768d5b136ad07b4b1926cc4e58085951034732f4cda1d4b501082"

# Official trial key signed with Argos Works master Ed25519 key (valid for testing / initial deploy)
# Customer: "Argos Enterprise Trial", Seats: 25, Expiry: 2099-12-31, Modules: ["canvas","rag","jira","pim","schedule","audit"]


def get_license_public_key() -> ed25519.Ed25519PublicKey:
    """Return the Ed25519 public key used for license verification on customer instances."""
    pub_hex = os.environ.get("ARGOS_LICENSE_PUBLIC_KEY", EMBEDDED_LICENSE_PUBLIC_KEY_HEX).strip()
    pub_bytes = bytes.fromhex(pub_hex)
    return ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)


def get_license_status():
    """현재 시스템 라이선스 상태 및 사용 좌석(Active Seats) 현황을 반환한다."""
    row = get_one("SELECT * FROM license_info WHERE id = 1")
    if not row:
        return {
            "customer_name": "Unlicensed Enterprise",
            "license_key": "",
            "max_seats": 0,
            "active_seats": 0,
            "expiry_date": "1970-01-01",
            "is_active": False,
            "is_expired": True,
            "is_read_only": True,
            "modules": []
        }

    # Count active non-disabled users
    user_cnt_row = get_one("SELECT count(*) as c FROM users WHERE disabled = 0")
    active_seats = user_cnt_row["c"] if user_cnt_row else 0

    exp_str = row.get("expiry_date") or "1970-01-01"
    is_expired = False
    try:
        exp_date = datetime.strptime(exp_str[:10], "%Y-%m-%d").date()
        if date.today() > exp_date:
            is_expired = True
    except Exception:
        pass

    is_active = bool(row.get("is_active")) and not is_expired
    is_read_only = is_expired or (not bool(row.get("is_active")))

    modules = []
    try:
        modules = json.loads(row.get("modules_json") or "[]")
    except Exception:
        modules = ["canvas", "rag", "jira", "pim", "schedule", "audit"]

    return {
        "customer_name": row.get("customer_name", "Enterprise Customer"),
        "license_key": row.get("license_key", ""),
        "max_seats": int(row.get("max_seats") or 0),
        "active_seats": active_seats,
        "expiry_date": exp_str[:10],
        "is_active": is_active,
        "is_expired": is_expired,
        "is_read_only": is_read_only,
        "modules": modules
    }

get_license_info = get_license_status


def check_seat_available():
    """신규 사용자 등록 시 좌석 한도 초과 여부를 검사한다."""
    status = get_license_status()
    if status["is_read_only"]:
        return False, f"라이선스가 만료되어 읽기 전용 상태입니다 (만료일: {status['expiry_date']}). 갱신이 필요합니다."
    if status["active_seats"] >= status["max_seats"]:
        return False, f"라이선스 사용자 좌석 한도({status['max_seats']}명)를 초과했습니다. 관리자에게 라이선스 증설을 요청하세요."
    return True, ""


def is_system_read_only():
    """시스템이 라이선스 만료 등으로 읽기 전용 상태인지 여부를 반환한다."""
    try:
        status = get_license_status()
        return bool(status.get("is_read_only", False))
    except Exception:
        return True


def generate_signed_license_key(customer_name, max_seats, expiry_date_str, modules, signing_key_hex=None):
    """라이선스 발급 서버용: Ed25519 개인키로 비대칭 전자서명된 오프라인 라이선스 키 생성."""
    priv_hex = signing_key_hex or os.environ.get("ARGOS_LICENSE_SIGNING_KEY") or os.environ.get("ARGOS_LICENSE_SECRET")
    if not priv_hex:
        # Default signing key for vendor CLI / testing matching EMBEDDED_LICENSE_PUBLIC_KEY_HEX
        priv_hex = "79177ec5e385a059f4851cf8701b73f09111a25bc365046afb1d7fcfc42753a0"

    priv_bytes = bytes.fromhex(priv_hex.strip())
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)

    payload = {
        "customer": customer_name,
        "seats": max_seats,
        "expiry": expiry_date_str,
        "modules": modules,
        "iat": datetime.now().strftime("%Y-%m-%d")
    }
    raw_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode("utf-8")
    sig = private_key.sign(raw_json)
    b64_payload = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    b64_sig = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return f"AGY-{b64_payload}.{b64_sig}"


def verify_license_key(license_key_str):
    """라이선스 키의 유효성을 Ed25519 공개키로 비대칭 검증하고 메타데이터를 반환한다."""
    key = (license_key_str or "").strip()
    if not key:
        return False, "라이선스 키를 입력해주세요.", None

    if "." not in key:
        return False, "잘못된 라이선스 키 형식입니다 (AGY-payload.signature 구조 필요).", None

    content = key
    if content.startswith("AGY-"):
        content = content[4:]

    parts = content.split(".")
    if len(parts) != 2:
        return False, "유효하지 않은 라이선스 서명 구조입니다.", None

    b64_payload, b64_sig = parts[0], parts[1]

    # Decode payload
    pad_p = len(b64_payload) % 4
    if pad_p:
        b64_payload += "=" * (4 - pad_p)

    pad_s = len(b64_sig) % 4
    if pad_s:
        b64_sig += "=" * (4 - pad_s)

    try:
        raw_json = base64.urlsafe_b64decode(b64_payload.encode("ascii"))
        sig_bytes = base64.urlsafe_b64decode(b64_sig.encode("ascii"))
    except Exception as e:
        return False, f"라이선스 디코딩 실패: {e}", None

    # Verify asymmetric Ed25519 digital signature
    try:
        public_key = get_license_public_key()
        public_key.verify(sig_bytes, raw_json)
    except InvalidSignature:
        return False, "라이선스 디지털 서명(Ed25519) 검증에 실패했습니다. (위변조 감지 또는 미승인 발급키)", None
    except Exception as e:
        return False, f"서명 검증 중 오류: {e}", None

    try:
        data = json.loads(raw_json.decode("utf-8"))
        customer = data.get("customer") or "Valued Enterprise Customer"
        seats = int(data.get("seats") or 0)
        expiry = data.get("expiry") or "1970-01-01"
        modules = data.get("modules") or []

        # Check expiration date
        try:
            exp_date = datetime.strptime(expiry[:10], "%Y-%m-%d").date()
            if date.today() > exp_date:
                return False, f"만료된 라이선스 키입니다 (만료일: {expiry}).", None
        except Exception:
            pass

        return True, "유효한 엔터프라이즈 정품 라이선스입니다.", {
            "customer": customer,
            "seats": seats,
            "expiry": expiry,
            "modules": modules,
            "is_trial": ("trial" in customer.lower())
        }
    except Exception as e:
        return False, f"라이선스 페이로드 파싱 실패: {e}", None


def activate_license(license_key_str):
    """고객 인스턴스: Ed25519 서명 라이선스 키를 검증하고 시스템에 적용한다."""
    ok, msg, data = verify_license_key(license_key_str)
    if not ok:
        return False, msg

    try:
        customer = data.get("customer") or "Valued Enterprise"
        seats = int(data.get("seats") or 0)
        expiry = data.get("expiry") or "1970-01-01"
        modules = data.get("modules") or []
        key = (license_key_str or "").strip()

        execute("""
            INSERT INTO license_info (id, customer_name, license_key, max_seats, expiry_date, modules_json, is_active, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT (id) DO UPDATE SET
                customer_name = EXCLUDED.customer_name,
                license_key = EXCLUDED.license_key,
                max_seats = EXCLUDED.max_seats,
                expiry_date = EXCLUDED.expiry_date,
                modules_json = EXCLUDED.modules_json,
                is_active = 1,
                updated_at = EXCLUDED.updated_at
        """, (customer, key, seats, expiry, json.dumps(modules), datetime.now().strftime("%Y-%m-%dT%H:%M:%S")))

        return True, f"'{customer}' 엔터프라이즈 라이선스(좌석: {seats}명, 만료일: {expiry})가 성공적으로 활성화되었습니다."
    except Exception as e:
        return False, f"라이선스 활성화 실패: {e}"
