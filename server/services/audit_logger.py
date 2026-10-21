# -*- coding: utf-8 -*-
"""audit_logger.py — Enterprise Immutable Audit Trail Engine for ARGOS WORKS.
Records who, when, where (IP), what action, target, and diff/details for all
critical system events (logins, records, PIM price modifications, backups, user role changes).
"""

import json
import logging
from datetime import datetime
from db import execute, query

logger = logging.getLogger(__name__)

def log_audit(session_or_user=None, ip=None, action="", target_type="", target_id="", details=None, session=None, **kwargs):
    """
    Append an immutable audit entry to audit_logs table.
    - session_or_user (or session): dict containing 'name', 'org', 'role', 'id' or username string
    - ip: client IP string
    - action: e.g., 'LOGIN', 'LOGOUT', 'RECORD_CREATE', 'RECORD_UPDATE', 'RECORD_DELETE', 'RECORD_VIEW', 'PIM_PRICE_UPDATE', 'BACKUP_CREATE', 'BACKUP_RESTORE', 'USER_ROLE_CHANGE'
    - target_type: 'record', 'product', 'user', 'backup', 'settings', 'auth'
    - target_id: identifier of affected item (e.g., 'DEV-102', 'PROD-CAM-01', user id)
    - details: dict with additional context (e.g., {"old_price": 50000, "new_price": 60000})
    """
    if session_or_user is None and session is not None:
        session_or_user = session
    try:
        user_id = None
        username = "anonymous"
        dept_id = ""

        if isinstance(session_or_user, dict):
            user_id = session_or_user.get("id") or session_or_user.get("userId")
            username = session_or_user.get("name") or session_or_user.get("username") or "unknown"
            dept_id = session_or_user.get("org") or session_or_user.get("dept_id") or ""
        elif isinstance(session_or_user, str) and session_or_user.strip():
            username = session_or_user.strip()

        details_json = "{}"
        if details is not None:
            if isinstance(details, dict):
                # Ensure no passwords or raw secret tokens get logged
                safe_details = dict(details)
                for secret_k in ("password", "token", "hash", "salt", "api_key", "secret"):
                    if secret_k in safe_details:
                        safe_details[secret_k] = "******"
                details_json = json.dumps(safe_details, ensure_ascii=False)
            elif isinstance(details, str):
                details_json = details

        execute(
            """INSERT INTO audit_logs (timestamp, user_id, username, dept_id, ip, action, target_type, target_id, details_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                user_id,
                username,
                dept_id,
                str(ip or "127.0.0.1"),
                action.upper(),
                target_type.lower(),
                str(target_id or ""),
                details_json
            )
        )
    except Exception as e:
        logger.error(f"[AuditLogger] Failed to write audit log: {e}")

def get_audit_logs(limit=100, action=None, username=None, user_name=None, target_type=None, from_date=None, to_date=None):
    """Query recent audit logs with optional filters."""
    if username is None and user_name is not None:
        username = user_name
    sql = "SELECT * FROM audit_logs WHERE 1=1"
    params = []

    if action:
        sql += " AND action = ?"
        params.append(action.upper())
    if username:
        sql += " AND username LIKE ?"
        params.append(f"%{username}%")
    if target_type:
        sql += " AND target_type = ?"
        params.append(target_type.lower())
    if from_date:
        sql += " AND timestamp >= ?"
        params.append(f"{from_date} 00:00:00")
    if to_date:
        sql += " AND timestamp <= ?"
        params.append(f"{to_date} 23:59:59")

    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 1000)))

    rows = query(sql, tuple(params))
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["details"] = json.loads(d.get("details_json") or "{}")
        except Exception:
            d["details"] = {}
        results.append(d)
    return results
