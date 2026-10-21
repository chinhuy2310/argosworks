# -*- coding: utf-8 -*-
"""license_manager.py — Enterprise License, Capacity & Expiration Engine for ARGOS WORKS.
Manages seats count (max active users), contract expiration date, offline activation,
and read-only mode enforcement upon license expiry.
"""

import os
import json
import base64
import hmac
import hashlib
from datetime import datetime, date
from db import query, get_one, execute

def get_license_secret():
    secret = os.environ.get("ARGOS_LICENSE_SECRET")
    if not secret:
        # Check master key or raise error/safe default for dev only
        secret = os.environ.get("JARVIS_MASTER_KEY")
    if not secret:
        raise RuntimeError("ARGOS_LICENSE_SECRET or JARVIS_MASTER_KEY must be set in environment for license signing/verification.")
    return secret

def get_license_status():
    """현재 시스템 라이선스 상태 및 사용 좌석(Active Seats) 현황을 반환한다."""
    row = get_one("SELECT * FROM license_info WHERE id = 1")
    if not row:
        return {
            "customer_name": "Argos Enterprise Trial",
            "license_key": "TRIAL",
            "max_seats": 25,
            "active_seats": 1,
            "expiry_date": "2099-12-31",
            "is_active": True,
            "is_expired": False,
            "is_read_only": False,
            "modules": ["canvas", "rag", "jira", "pim", "schedule", "audit"]
        }

    # Count active non-disabled users
    user_cnt_row = get_one("SELECT count(*) as c FROM users WHERE disabled = 0")
    active_seats = user_cnt_row["c"] if user_cnt_row else 0

    exp_str = row.get("expiry_date") or "2099-12-31"
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
        "max_seats": int(row.get("max_seats") or 25),
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
        return False

def generate_signed_license_key(customer_name, max_seats, expiry_date_str, modules):
    """라이선스 발급 서버용: HMAC 서명된 오프라인 라이선스 키 생성."""
    payload = {
        "customer": customer_name,
        "seats": max_seats,
        "expiry": expiry_date_str,
        "modules": modules,
        "iat": datetime.now().strftime("%Y-%m-%d")
    }
    raw_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode("utf-8")
    sig = hmac.new(get_license_secret().encode("utf-8"), raw_json, hashlib.sha256).hexdigest()[:16]
    b64_payload = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    return f"AGY-{b64_payload}.{sig}"

def verify_license_key(license_key_str):
    """라이선스 키의 유효성을 검증하고 포함된 메타데이터(고객사, 좌석수, 만료일 등)를 반환한다."""
    key = (license_key_str or "").strip()
    if not key:
        return False, "라이선스 키를 입력해주세요.", None

    if key.upper() in ("TRIAL", "TRIAL-ARGOS", "ARGOS-TRIAL-COMMERCIAL-2026", "TRIAL-ENTERPRISE"):
        return True, "유효한 평가판(Trial) 라이선스입니다.", {
            "customer": "Argos Enterprise Trial",
            "seats": 25,
            "expiry": "2099-12-31",
            "modules": ["canvas", "rag", "jira", "pim", "schedule", "audit"],
            "is_trial": True
        }

    if "." not in key:
        return False, "잘못된 라이선스 키 형식입니다 (AGY-xxxx.xxxx 구조 필요).", None

    content = key
    if content.startswith("AGY-"):
        content = content[4:]

    parts = content.split(".")
    if len(parts) != 2:
        return False, "유효하지 않은 라이선스 서명 구조입니다.", None

    b64_payload, sig = parts[0], parts[1]
    pad = len(b64_payload) % 4
    if pad:
        b64_payload += "=" * (4 - pad)

    try:
        raw_json = base64.urlsafe_b64decode(b64_payload.encode("ascii"))
        expected_sig = hmac.new(get_license_secret().encode("utf-8"), raw_json, hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            return False, "라이선스 디지털 서명 검증에 실패했습니다. (위변조 감지)", None

        data = json.loads(raw_json.decode("utf-8"))
        customer = data.get("customer") or "Valued Enterprise Customer"
        seats = int(data.get("seats") or 25)
        expiry = data.get("expiry") or "2099-12-31"
        modules = data.get("modules") or ["canvas", "rag", "jira", "pim", "schedule", "audit"]

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
            "is_trial": False
        }
    except Exception as e:
        return False, f"라이선스 검증 실패: {e}", None


def activate_license(license_key_str):
    """고객 인스턴스: 오프라인 라이선스 키를 검증하고 시스템에 적용한다."""
    ok, msg, data = verify_license_key(license_key_str)
    if not ok:
        return False, msg

    try:
        customer = data.get("customer") or "Valued Enterprise"
        seats = int(data.get("seats") or 25)
        expiry = data.get("expiry") or "2099-12-31"
        modules = data.get("modules") or ["canvas", "rag", "jira", "pim", "schedule", "audit"]
        key = (license_key_str or "").strip()

        execute("""
            UPDATE license_info 
            SET customer_name = ?, license_key = ?, max_seats = ?, expiry_date = ?, modules_json = ?, is_active = 1, updated_at = ?
            WHERE id = 1
        """, (customer, key, seats, expiry, json.dumps(modules), datetime.now().strftime("%Y-%m-%dT%H:%M:%S")))

        return True, f"'{customer}' 엔터프라이즈 라이선스(좌석: {seats}명, 만료일: {expiry})가 성공적으로 활성화되었습니다."
    except Exception as e:
        return False, f"라이선스 활성화 실패: {e}"
