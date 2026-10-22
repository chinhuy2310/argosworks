"""auth.py — 인증·세션 관리 (SQLite 버전)
기존 JSON 파일(accounts.json, sessions.json) 대신 SQLite DB를 사용한다.
모든 함수 시그니처와 반환 형식은 100% 유지된다.
"""
import hashlib
import hmac
import re
import secrets
import threading
import os
import time

from db import query, get_one, execute, transaction

PBKDF2_ROUNDS = 600000
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(SERVER_DIR)


def account_key(name, org):
    """계정 복합 키 (기존 호환)."""
    return (name or "").strip() + "|" + (org or "").strip()


def read_accounts():
    """모든 계정을 반환한다. 기존 API 호환: dict keyed by 'name|org'."""
    rows = query("SELECT id, name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at FROM users")
    result = {}
    for r in rows:
        key = account_key(r["name"], r["dept_id"])
        result[key] = {
            "id": r["id"],
            "name": r["name"],
            "username": r.get("username") or r["name"],
            "org": r["dept_id"],
            "email": r["email"],
            "salt": r["salt"],
            "hash": r["password_hash"],
            "isAdmin": bool(r.get("is_admin")),
            "role": r.get("role") or "member",
            "disabled": r.get("disabled") or 0,
            "status": r.get("status") or "active",
            "createdAt": r["created_at"],
        }
    return result


def get_user_by_id(user_id):
    """ID로 단일 사용자를 조회한다 (인덱스 활용)."""
    if not user_id:
        return None
    return get_one(
        """SELECT id, name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at
           FROM users WHERE id = ? LIMIT 1""",
        (user_id,)
    )


def get_user_by_login(login_id, org=None):
    """
    로그인 식별자(아이디, 이메일, 사원명)로 사용자를 고속 조회한다 (인덱스 활용).
    전체 테이블을 메모리에 풀스캔하지 않고 DB 인덱스로 직접 조회한다.
    """
    login_id = (login_id or "").strip()
    if not login_id:
        return None
    login_lower = login_id.lower()

    # 1. username 매칭 (대소문자 무시)
    row = get_one(
        """SELECT id, name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at
           FROM users
           WHERE LOWER(username) = ?
           LIMIT 1""",
        (login_lower,)
    )
    if row:
        return row

    # 2. email 매칭 (대소문자 무시)
    row = get_one(
        """SELECT id, name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at
           FROM users
           WHERE email != '' AND LOWER(email) = ?
           LIMIT 1""",
        (login_lower,)
    )
    if row:
        return row

    # 3. 소속 부서 + 이름 매칭 (동명이인 방지를 위해 부서가 지정된 경우만 허용)
    if org:
        row = get_one(
            """SELECT id, name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at
               FROM users
               WHERE LOWER(name) = ? AND LOWER(dept_id) = ?
               LIMIT 1""",
            (login_lower, str(org).strip().lower())
        )
        if row:
            return row

    # 부서 지정 없는 사원명 단독 매칭은 타 부서 동명이인의 계정 탈취 및 권한 상승을 방지하기 위해 불허
    return None


def create_user(name, username, org, email, salt, hash_pwd, role="member", is_admin=False, status="active", disabled=0, hash_algo="pbkdf2_sha256", iterations=PBKDF2_ROUNDS):
    """
    단일 사용자를 원자적(Atomic)으로 생성한다.
    동시성 요청 시 Race Condition 및 중복 username/email을 DB 제약조건과 함께 안전하게 방어한다.
    """
    name = (name or "").strip()
    username = (username or name).strip()
    org = (org or "").strip()
    email = (email or "").strip()

    if not username:
        raise ValueError("아이디(Username)를 입력해주세요.")
    if not name:
        raise ValueError("이름(Name)을 입력해주세요.")

    # 1. 중복 username 검증
    dup_user = get_one("SELECT id FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1", (username,))
    if dup_user:
        raise ValueError("이미 사용 중인 ArgosWorks ID입니다. 다른 ID를 입력해주세요.")

    # 2. 중복 email 검증 (email이 제공된 경우)
    if email:
        dup_email = get_one("SELECT id FROM users WHERE email != '' AND LOWER(email) = LOWER(?) LIMIT 1", (email,))
        if dup_email:
            raise ValueError("이미 등록된 이메일 주소입니다.")

    # 3. 동일 소속 + 이름 중복 검증
    dup_name_dept = get_one("SELECT id FROM users WHERE name = ? AND dept_id = ? LIMIT 1", (name, org))
    if dup_name_dept:
        raise ValueError("해당 소속에 이미 동일한 이름의 사용자가 존재합니다.")

    from datetime import datetime
    now_iso = datetime.now().isoformat()

    def _insert(conn):
        cur = conn.cursor()
        if org:
            dept_exists = cur.execute("SELECT 1 FROM departments WHERE id = ?", (org,)).fetchone()
            if not dept_exists:
                cur.execute(
                    "INSERT OR IGNORE INTO departments(id, name, color_index) VALUES (?, ?, 1)",
                    (org, org)
                )
        cur.execute(
            """INSERT INTO users(name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at, hash_algo, iterations)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, username, org, email, salt, hash_pwd, 1 if is_admin else 0, role, disabled, status, now_iso, hash_algo, iterations)
        )

    transaction(_insert)
    return get_user_by_login(username)


def safe_delete_user(user_id):
    """
    사용자를 안전하게 삭제한다:
    - 외래키 제약조건 위반(ForeignKeyViolation) 및 고아 FK 방지를 위해
      records.assignee_id 및 schedule_events.owner_id를 동일 트랜잭션에서 NULL 처리.
    - 해당 사용자의 세션 및 일정 참여자 목록 정리 후 사용자 삭제.
    """
    user = get_one("SELECT * FROM users WHERE id = ? LIMIT 1", (user_id,))
    if not user:
        return False
    user_name = user.get("name", "")
    user_dept = user.get("dept_id", "")

    def _do_del(conn):
        cur = conn.cursor()
        # 1. 업무 카드 assignee_id NULL 처리 (고아 FK 방지)
        cur.execute("UPDATE records SET assignee_id = NULL WHERE assignee_id = ?", (user_id,))
        # 2. 일정 소유자 owner_id NULL 처리
        cur.execute("UPDATE schedule_events SET owner_id = NULL WHERE owner_id = ?", (user_id,))
        # 3. 일정 참여자 항목 정리
        cur.execute("DELETE FROM schedule_participants WHERE user_name = ?", (user_name,))
        # 4. 세션 만료
        cur.execute("DELETE FROM sessions WHERE user_name = ? AND user_dept_id = ?", (user_name, user_dept))
        # 5. 사용자 삭제
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))

    transaction(_do_del)
    return True


def write_accounts(accounts):
    """계정 목록을 갱신한다 (기존 API 호환). 동시성 데이터 유실을 방지하기 위해 일괄 DELETE를 수행하지 않는다."""
    def _do(conn):
        cur = conn.cursor()
        existing = {}
        for row in cur.execute("SELECT id, name, dept_id FROM users").fetchall():
            uid = row["id"] if isinstance(row, dict) else row[0]
            uname = row["name"] if isinstance(row, dict) else row[1]
            udept = row["dept_id"] if isinstance(row, dict) else row[2]
            existing[account_key(uname, udept)] = uid

        for key, acc in accounts.items():
            name = acc.get("name", "")
            username = acc.get("username") or name
            org = acc.get("org", "")
            akey = account_key(name, org)

            if akey in existing:
                cur.execute(
                    """UPDATE users SET username=?, email=?, salt=?, password_hash=?, created_at=?
                       WHERE id=?""",
                    (username, acc.get("email", ""), acc.get("salt", ""),
                     acc.get("hash", ""), acc.get("createdAt", ""),
                     existing[akey])
                )
            else:
                dept_id = org
                if dept_id:
                    dept_exists = cur.execute(
                        "SELECT 1 FROM departments WHERE id = ?", (dept_id,)
                    ).fetchone()
                    if not dept_exists:
                        cur.execute(
                            "INSERT OR IGNORE INTO departments(id, name, color_index) VALUES (?, ?, 1)",
                            (dept_id, dept_id)
                        )
                is_adm = 1 if (acc.get("isAdmin") or acc.get("is_admin")) else 0
                role = "admin" if is_adm else acc.get("role", "member")
                status = "active" if is_adm else acc.get("status", "pending")
                disabled = 0 if is_adm else acc.get("disabled", 1)
                cur.execute(
                    """INSERT INTO users(name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, username, dept_id, acc.get("email", ""), acc.get("salt", ""),
                     acc.get("hash", ""), is_adm, role, disabled, status, acc.get("createdAt", ""))
                )

    transaction(_do)


def hash_password(password, salt_hex=None, iterations=PBKDF2_ROUNDS):
    """PBKDF2 비밀번호 해싱 (기본 600,000회 반복)."""
    salt = os.urandom(16) if salt_hex is None else bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, iterations)
    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, hash_hex, iterations=None, user_id=None):
    """
    비밀번호 검증 및 자동 점진적 보안 업그레이드(Auto-upgrade hash to 600k iterations).
    단일 반복 횟수로 검증하여 잘못된 비밀번호 시 CPU 낭비(DoS 위험)를 방지한다.
    """
    if not salt_hex or not hash_hex:
        return False

    target_iters = iterations
    if not target_iters and user_id:
        try:
            row = get_one("SELECT iterations FROM users WHERE id = ? LIMIT 1", (user_id,))
            if row and row.get("iterations"):
                target_iters = int(row["iterations"])
        except Exception:
            pass

    if target_iters:
        try:
            _, digest_hex = hash_password(password, salt_hex, iterations=target_iters)
            if hmac.compare_digest(digest_hex, hash_hex):
                if target_iters < PBKDF2_ROUNDS and user_id:
                    try:
                        new_salt, new_hash = hash_password(password, iterations=PBKDF2_ROUNDS)
                        execute(
                            "UPDATE users SET salt = ?, password_hash = ?, iterations = ?, hash_algo = 'pbkdf2_sha256' WHERE id = ?",
                            (new_salt, new_hash, PBKDF2_ROUNDS, user_id)
                        )
                    except Exception:
                        pass
                return True
        except Exception:
            return False
        return False

    try:
        _, digest_hex = hash_password(password, salt_hex, iterations=PBKDF2_ROUNDS)
        if hmac.compare_digest(digest_hex, hash_hex):
            return True
    except Exception:
        pass

    try:
        _, digest_hex_100k = hash_password(password, salt_hex, iterations=100000)
        if hmac.compare_digest(digest_hex_100k, hash_hex):
            if user_id:
                try:
                    new_salt, new_hash = hash_password(password, iterations=PBKDF2_ROUNDS)
                    execute(
                        "UPDATE users SET salt = ?, password_hash = ?, iterations = ?, hash_algo = 'pbkdf2_sha256' WHERE id = ?",
                        (new_salt, new_hash, PBKDF2_ROUNDS, user_id)
                    )
                except Exception:
                    pass
            return True
    except Exception:
        pass

    return False

def is_admin_user(user_or_session, email=None):
    """
    사용자가 Admin 권한(users.role == 'admin')을 가지고 있는지 ID/고유계정 기준으로 엄격하게 판정한다.
    동명이인 혼동 및 OR 쿼리로 인한 권한 상승 취약점을 완전히 제거하고 users.id / username을 기준으로 검증한다.
    """
    if not user_or_session:
        return False

    # 1. Dict 형태 세션 또는 사용자 객체
    if isinstance(user_or_session, dict):
        u_id = user_or_session.get("id") or user_or_session.get("user_id")
        if u_id:
            row = get_one("SELECT role, is_admin FROM users WHERE id = ? LIMIT 1", (u_id,))
            return bool(row and (row.get("role") == "admin" or row.get("is_admin") == 1))
        username = user_or_session.get("username")
        if username:
            row = get_one("SELECT role, is_admin FROM users WHERE username != '' AND LOWER(username) = LOWER(?) LIMIT 1", (username,))
            return bool(row and (row.get("role") == "admin" or row.get("is_admin") == 1))
        # ID나 Username이 없는 레거시 세션인 경우 세션 내 명시적 admin role 검증
        if user_or_session.get("role") == "admin":
            return True
        return False

    # 2. Integer user_id 또는 Numeric ID string
    if isinstance(user_or_session, int) or (isinstance(user_or_session, str) and user_or_session.isdigit()):
        row = get_one("SELECT role, is_admin FROM users WHERE id = ? LIMIT 1", (int(user_or_session),))
        return bool(row and (row.get("role") == "admin" or row.get("is_admin") == 1))

    # 3. String username
    if isinstance(user_or_session, str):
        login_str = user_or_session.strip()
        if login_str:
            row = get_one("SELECT role, is_admin FROM users WHERE username != '' AND LOWER(username) = LOWER(?) LIMIT 1", (login_str,))
            return bool(row and (row.get("role") == "admin" or row.get("is_admin") == 1))

    return False


def get_user_role(user_or_session):
    """사용자의 시스템 권한 등급을 반환한다 ('admin', 'manager', 'member', 'viewer')."""
    if not user_or_session:
        return "viewer"
    if isinstance(user_or_session, dict):
        role = user_or_session.get("role")
        if role in ("admin", "manager", "member", "viewer"):
            return role
        u_id = user_or_session.get("id") or user_or_session.get("user_id")
        if u_id:
            row = get_one("SELECT role, is_admin FROM users WHERE id = ? LIMIT 1", (u_id,))
            if row:
                if row.get("role") == "admin" or row.get("is_admin") == 1:
                    return "admin"
                return row.get("role") or "member"
    if is_admin_user(user_or_session):
        return "admin"
    return "member"

def is_manager_or_admin(user_or_session):
    """사용자가 Manager(부서장) 이상(Admin/Master 포함)의 관리 권한을 가지고 있는지 판정한다."""
    if is_admin_user(user_or_session):
        return True
    role = get_user_role(user_or_session)
    return role in ("admin", "manager")


def can_view_record(user_or_session, record):
    """
    레코드 열람 권한 판정:
    - admin: 모든 레코드 열람 가능
    - is_private == 1: 작성자, 담당자, 부서장(manager), admin만 열람 가능
    - manager: 자기 부서 전체 + 타 부서의 일반 공개 레코드 열람 가능
    - member / viewer: 자기 부서 레코드 또는 본인이 담당자/참여자로 지정된 레코드 열람 가능
    (보안 강화: 동명이인 타 부서 충돌 방지 및 정확한 식별자 매칭)
    """
    if not user_or_session:
        return False
    role = get_user_role(user_or_session)
    if role == "admin":
        return True

    u_id = user_or_session.get("id") or user_or_session.get("user_id")
    u_name = user_or_session.get("name", "").strip().lower()
    u_username = user_or_session.get("username", "").strip().lower()
    u_email = user_or_session.get("email", "").strip().lower()
    u_dept = (user_or_session.get("org") or user_or_session.get("dept_id") or "").strip().lower()

    rec_dept = (record.get("dept_id") or record.get("org") or "").strip().lower()
    rec_assignee_id = record.get("assignee_id")
    rec_assignee = (record.get("assignee_name") or record.get("assignee") or "").strip().lower()
    rec_assignee_email = (record.get("assignee_email") or "").strip().lower()
    
    raw_participants = record.get("participants") or ""
    parts = [p.strip().lower() for p in re.split(r"[,;/\n]+", str(raw_participants)) if p.strip()]

    is_same_dept = bool(u_dept and u_dept == rec_dept)
    is_private = bool(record.get("is_private"))

    # 정확한 담당자/참여자 매칭:
    # 비공개 레코드(is_private=1)는 동명이인 타 부서 유출 방지를 위해 이름 단독 매칭 시 동일 부서 필수 검증
    is_involved = False
    if u_id and rec_assignee_id and str(u_id) == str(rec_assignee_id):
        is_involved = True
    elif u_username and u_username == rec_assignee:
        is_involved = True
    elif u_email and rec_assignee_email and u_email == rec_assignee_email:
        is_involved = True
    elif u_name and u_name == rec_assignee:
        if not is_private or is_same_dept or not rec_dept:
            is_involved = True
    elif u_username and u_username in parts:
        is_involved = True
    elif u_name and u_name in parts:
        if not is_private or is_same_dept or not rec_dept:
            is_involved = True

    is_same_dept = bool(u_dept and u_dept == rec_dept)
    is_private = bool(record.get("is_private"))

    if is_private:
        if is_involved:
            return True
        if is_same_dept and role == "manager":
            return True
        return False

    if is_same_dept:
        return True
    if is_involved:
        return True
    if role == "manager":
        return True

    return False

def can_modify_record(user_or_session, record):
    """
    레코드 수정/삭제 권한 판정:
    - viewer는 읽기 전용 역할로 무조건 차단 (403)
    - admin은 전체 수정 가능
    - manager는 자기 부서 레코드 수정 가능
    - member는 자신이 담당자인 레코드만 수정 가능 (동명이인 타 부서 격리)
    """
    if not user_or_session:
        return False
    role = get_user_role(user_or_session)
    if role == "admin":
        return True
    if role == "viewer":
        return False

    u_id = user_or_session.get("id") or user_or_session.get("user_id")
    u_name = user_or_session.get("name", "").strip().lower()
    u_username = user_or_session.get("username", "").strip().lower()
    u_dept = (user_or_session.get("org") or user_or_session.get("dept_id") or "").strip().lower()

    rec_dept = (record.get("dept_id") or record.get("org") or "").strip().lower()
    rec_assignee_id = record.get("assignee_id")
    rec_assignee = (record.get("assignee_name") or record.get("assignee") or "").strip().lower()

    if role == "manager" and u_dept == rec_dept:
        return True
    if u_id and rec_assignee_id and str(u_id) == str(rec_assignee_id):
        return True
    if u_username and u_username == rec_assignee:
        return True
    if u_name and u_name == rec_assignee:
        is_private = bool(record.get("is_private"))
        if not is_private or u_dept == rec_dept or not rec_dept:
            return True

    return False

def visible_records(session, records=None):
    """
    단일 권한 진실의 원천 (Single Source of Truth).
    N+1 쿼리 방지: role을 1회만 계산하고 모든 레코드 필터링에 재사용한다.
    """
    if not session:
        return []
    if records is None:
        from services.data_store import read_records
        records = read_records()
    if is_admin_user(session):
        return list(records)
    role = get_user_role(session)
    sess_cached = dict(session)
    sess_cached["role"] = role
    return [r for r in records if can_view_record(sess_cached, r)]

def can_view_pim_price(user_or_session):
    """PIM 제품 기준 가격 열람 권한: Admin 및 영업/경영 부서만 허용 (일반 엔지니어/타 부서에는 마스킹)"""
    if not user_or_session:
        return False
    role = get_user_role(user_or_session)
    if role == "admin":
        return True
    dept = (user_or_session.get("org") or user_or_session.get("dept_id") or "").lower()
    if dept in ("sales", "biz", "exec", "management", "경영", "영업"):
        return True
    return False


def can_modify_pim(user_or_session):
    """PIM 제품 및 가격 수정 권한: Admin 및 영업/경영 책임자만 허용"""
    if not user_or_session:
        return False
    role = get_user_role(user_or_session)
    if role == "admin":
        return True
    if role == "manager":
        dept = (user_or_session.get("org") or user_or_session.get("dept_id") or "").lower()
        if dept in ("sales", "biz", "exec", "management", "경영", "영업"):
            return True
    return False


# ---------------------------------------------------------------------------
# 세션 관리 (SQLite sessions table) & 로그인 보안 제어
# ---------------------------------------------------------------------------
_session_lock = threading.Lock()
_login_failures_lock = threading.Lock()
_login_failures = {}  # key: "ip:user" -> [timestamp, timestamp, ...]

DEFAULT_SESSION_TTL_HOURS = 24

def get_session_ttl_seconds():
    """세션 유효 기간(초)을 반환한다 (환경변수 SESSION_TTL_HOURS 지원, 기본 24시간)."""
    try:
        val = int(os.environ.get("SESSION_TTL_HOURS", DEFAULT_SESSION_TTL_HOURS))
        return max(1, val) * 3600
    except Exception:
        return DEFAULT_SESSION_TTL_HOURS * 3600

def check_login_rate_limit(ip, identifier):
    """
    무차별 대입 공격(Brute-force) 방어 (DB 영속화):
    계정별 독립 임시 잠금 (동일 계정 15분 내 5회 실패 시 해당 계정 잠금)
    IP별 DoS 방어 (동일 IP 15분 내 30회 실패 시 해당 IP 차단)
    특정 사용자 실패로 타 사용자가 차단되는 현상 및 IP 리셋 우회 공격 방어.
    """
    now = time.time()
    cutoff = now - 900
    ident = (identifier or '').strip().lower()
    try:
        # 1. Target account lockout: 5 failures within 15 mins locks that account
        if ident:
            row_user = get_one(
                "SELECT COUNT(*) as cnt, MIN(failed_at) as earliest FROM login_attempts WHERE identifier = ? AND failed_at > ?",
                (ident, cutoff)
            )
            cnt_user = row_user["cnt"] if row_user else 0
            if cnt_user >= 5:
                earliest = row_user["earliest"] if row_user and row_user.get("earliest") else cutoff
                remaining = int(900 - (now - earliest))
                mins = max(1, remaining // 60)
                return False, f"보안 경고: 해당 계정의 로그인 실패 횟수 초과로 임시 잠금되었습니다. {mins}분 후 다시 시도하세요."

        # 2. IP-level brute-force flood defense: 30 failures from same IP within 15 mins blocks IP
        row_ip = get_one(
            "SELECT COUNT(*) as cnt, MIN(failed_at) as earliest FROM login_attempts WHERE ip = ? AND failed_at > ?",
            (ip, cutoff)
        )
        cnt_ip = row_ip["cnt"] if row_ip else 0
        if cnt_ip >= 30:
            earliest = row_ip["earliest"] if row_ip and row_ip.get("earliest") else cutoff
            remaining = int(900 - (now - earliest))
            mins = max(1, remaining // 60)
            return False, f"보안 경고: 비정상적인 로그인 시도로 인해 IP가 임시 차단되었습니다. {mins}분 후 다시 시도하세요."
    except Exception:
        # Fallback to in-memory if DB fails
        key = f"{ip}:{ident}"
        with _login_failures_lock:
            attempts = [t for t in _login_failures.get(key, []) if now - t < 900]
            _login_failures[key] = attempts
            if len(attempts) >= 5:
                remaining = int(900 - (now - attempts[0]))
                mins = max(1, remaining // 60)
                return False, f"보안 경고: 로그인 시도 실패 횟수 초과로 계정이 임시 잠금되었습니다. {mins}분 후 다시 시도하세요."
    return True, ""

def record_login_failure(ip, identifier):
    """로그인 실패 시각 기록 (DB 및 메모리 동기화)."""
    now = time.time()
    ident = (identifier or '').strip().lower()
    try:
        execute("INSERT INTO login_attempts (ip, identifier, failed_at) VALUES (?, ?, ?)", (ip, ident, now))
        # Cleanup old attempts > 24 hours
        execute("DELETE FROM login_attempts WHERE failed_at < ?", (now - 86400,))
    except Exception:
        pass
    key = f"{ip}:{ident}"
    with _login_failures_lock:
        attempts = [t for t in _login_failures.get(key, []) if now - t < 900]
        attempts.append(now)
        _login_failures[key] = attempts

def clear_login_failures(ip, identifier):
    """로그인 성공 시 해당 계정의 실패 기록만 초기화 (IP 레코드 삭제 방지하여 브루트포스 리셋 공격 차단)."""
    ident = (identifier or '').strip().lower()
    if ident:
        try:
            execute("DELETE FROM login_attempts WHERE identifier = ?", (ident,))
        except Exception:
            pass
    key = f"{ip}:{ident}"
    with _login_failures_lock:
        if key in _login_failures:
            del _login_failures[key]

def hash_session_token(token: str) -> str:
    """Computes SHA-256 hash of session token for secure database storage."""
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_session(name_or_user_id, org=None, email=None, user_id=None):
    """
    새 로그인 세션을 생성한다.
    세션 토큰을 SHA-256으로 해시하여 DB에 안전하게 저장한다 (Plaintext 세션 노출 방지).
    """
    u_id = user_id
    name = str(name_or_user_id or "")
    if isinstance(name_or_user_id, int):
        u_id = name_or_user_id
        u_row = get_user_by_id(u_id)
        if u_row:
            name = u_row.get("name") or name
            org = org or u_row.get("dept_id")
            email = email or u_row.get("email")
    elif not u_id:
        u_row = get_user_by_login(name, org)
        if not u_row and org:
            u_row = get_one("SELECT id, name, dept_id, email, role, is_admin FROM users WHERE LOWER(name) = ? AND LOWER(dept_id) = ? LIMIT 1", (name.lower(), str(org).lower()))
        if not u_row and email:
            u_row = get_one("SELECT id, name, dept_id, email, role, is_admin FROM users WHERE LOWER(email) = ? LIMIT 1", (email.lower(),))
        if not u_row:
            u_row = get_one("SELECT id, name, dept_id, email, role, is_admin FROM users WHERE LOWER(username) = ? LIMIT 1", (name.lower(),))
        if u_row:
            u_id = u_row["id"]
            name = u_row.get("name") or name
            org = org or u_row.get("dept_id")
            email = email or u_row.get("email")

    token = secrets.token_hex(24)
    token_hash = hash_session_token(token)
    ts = time.time()
    is_admin = is_admin_user(u_id or name)

    execute(
        """INSERT INTO sessions(token, user_id, user_name, user_dept_id, user_email, is_admin, created_at, last_active_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (token_hash, u_id, name, org or "", email or "", 1 if is_admin else 0, ts, ts)
    )
    return token

def get_session(token):
    """토큰으로 세션 정보를 반환한다 (SHA-256 해시 조회 및 슬라이딩 세션 갱신)."""
    if not token:
        return None

    token_hash = hash_session_token(token)
    row = get_one(
        """SELECT s.token, s.user_id, s.user_name, s.user_dept_id, s.user_email, s.created_at, s.last_active_at,
                  u.id AS u_id, u.name AS u_name, u.username AS u_username, u.dept_id AS u_dept_id,
                  u.email AS u_email, u.role AS u_role, u.is_admin AS u_is_admin,
                  u.disabled AS u_disabled, u.status AS u_status
           FROM sessions s
           LEFT JOIN users u ON (s.user_id IS NOT NULL AND s.user_id = u.id)
                             OR (s.user_id IS NULL AND LOWER(s.user_name) = LOWER(u.name) AND LOWER(s.user_dept_id) = LOWER(u.dept_id))
           WHERE s.token = ? OR s.token = ?""",
        (token_hash, token)
    )
    if not row:
        return None

    created_at = row.get("created_at") or 0
    last_active = row.get("last_active_at") or created_at
    now = time.time()
    ttl = get_session_ttl_seconds()

    # 슬라이딩 유효기간(Sliding Expiration): 마지막 활동 후 ttl 경과 시 만료
    if now - last_active > ttl:
        try:
            execute("DELETE FROM sessions WHERE token = ? OR token = ?", (token_hash, token))
        except Exception:
            pass
        return None

    # 활동 중인 세션은 5분마다 last_active_at 슬라이딩 갱신
    if now - last_active > 300:
        try:
            execute("UPDATE sessions SET last_active_at = ? WHERE token = ? OR token = ?", (now, token_hash, token))
        except Exception:
            pass

    u_id = row.get("u_id")
    if not u_id:
        return None
    if row.get("u_disabled") or row.get("u_status") != "active":
        return None

    user_role = row.get("u_role") or "member"
    is_admin = bool(user_role == "admin" or row.get("u_is_admin") == 1)
    if is_admin:
        user_role = "admin"

    return {
        "id": u_id,
        "user_id": u_id,
        "name": row.get("u_name") or row["user_name"],
        "username": row.get("u_username") or row["user_name"],
        "org": row.get("u_dept_id") or row["user_dept_id"],
        "dept_id": row.get("u_dept_id") or row["user_dept_id"],
        "email": row.get("u_email") or row["user_email"],
        "isAdmin": is_admin,
        "is_admin": is_admin,
        "role": user_role,
        "disabled": row.get("u_disabled") or 0,
        "status": row.get("u_status") or "active",
        "ts": created_at,
        "last_active": last_active
    }

def delete_session(token):
    """단일 세션 만료 (로그아웃)."""
    if token:
        token_hash = hash_session_token(token)
        try:
            execute("DELETE FROM sessions WHERE token = ? OR token = ?", (token_hash, token))
        except Exception:
            pass

def rotate_session(old_token):
    """권한 변경 또는 주기적 세션 토큰 교체 (Session Rotation)."""
    sess = get_session(old_token)
    if not sess:
        return None
    delete_session(old_token)
    return create_session(
        name_or_user_id=sess["name"],
        org=sess["org"],
        email=sess["email"],
        user_id=sess["id"]
    )

def delete_all_user_sessions(user_id_or_name):
    """해당 사용자의 모든 기기 세션 강제 만료 (Logout from all devices)."""
    if user_id_or_name is not None and user_id_or_name != "":
        try:
            if isinstance(user_id_or_name, int) or (isinstance(user_id_or_name, str) and str(user_id_or_name).isdigit()):
                execute("DELETE FROM sessions WHERE user_id = ?", (int(user_id_or_name),))
            else:
                execute("DELETE FROM sessions WHERE user_name = ? OR user_id IN (SELECT id FROM users WHERE username = ?)", (str(user_id_or_name), str(user_id_or_name)))
        except Exception:
            pass

def cleanup_expired_sessions():
    """주기적으로 만료된 세션을 정리한다."""
    cutoff = time.time() - get_session_ttl_seconds()
    try:
        execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
    except Exception:
        pass


