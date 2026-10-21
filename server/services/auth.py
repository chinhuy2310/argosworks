"""auth.py — 인증·세션 관리 (SQLite 버전)
기존 JSON 파일(accounts.json, sessions.json) 대신 SQLite DB를 사용한다.
모든 함수 시그니처와 반환 형식은 100% 유지된다.
"""
import hashlib
import hmac
import secrets
import threading
import os
import time

from db import query, get_one, execute, transaction

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

    # 3. 소속 부서 + 이름 매칭
    if org:
        row = get_one(
            """SELECT id, name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at
               FROM users
               WHERE name = ? AND dept_id = ?
               LIMIT 1""",
            (login_id, org)
        )
        if row:
            return row

    # 4. 사원명 단독 매칭 (대소문자 무시)
    return get_one(
        """SELECT id, name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at
           FROM users
           WHERE LOWER(name) = ?
           LIMIT 1""",
        (login_lower,)
    )


def create_user(name, username, org, email, salt, hash_pwd, role="member", is_admin=False, status="active", disabled=0):
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
            """INSERT INTO users(name, username, dept_id, email, salt, password_hash, is_admin, role, disabled, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, username, org, email, salt, hash_pwd, 1 if is_admin else 0, role, disabled, status, now_iso)
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


def hash_password(password, salt_hex=None):
    """PBKDF2 비밀번호 해싱."""
    salt = os.urandom(16) if salt_hex is None else bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, 100000)
    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, hash_hex):
    """비밀번호 검증."""
    if not salt_hex or not hash_hex:
        return False
    try:
        _, digest_hex = hash_password(password, salt_hex)
    except Exception:
        return False
    return hmac.compare_digest(digest_hex, hash_hex)


def is_admin_user(user_or_session, email=None):
    """사용자가 Admin 권한(DB role/is_admin)을 가지고 있는지 판정한다."""
    if isinstance(user_or_session, dict):
        if user_or_session.get("isAdmin") or user_or_session.get("is_admin") or user_or_session.get("role") == "admin":
            return True
        name = user_or_session.get("username") or user_or_session.get("name", "")
        email = user_or_session.get("email", "") or email or ""
    else:
        name = str(user_or_session or "")
        email = str(email or "")

    name_clean = (name or "").strip()
    email_clean = (email or "").strip()

    # 1. DB의 users 테이블에서 is_admin / role 확인 (표준 DB 권한 관리)
    if name_clean or email_clean:
        try:
            if name_clean and email_clean:
                row = get_one("SELECT is_admin, role FROM users WHERE username = ? OR name = ? OR email = ? ORDER BY is_admin DESC LIMIT 1", (name_clean, name_clean, email_clean))
            elif name_clean:
                row = get_one("SELECT is_admin, role FROM users WHERE username = ? OR name = ? ORDER BY is_admin DESC LIMIT 1", (name_clean, name_clean))
            else:
                row = get_one("SELECT is_admin, role FROM users WHERE email = ? ORDER BY is_admin DESC LIMIT 1", (email_clean,))
            if row and (row.get("is_admin") or row.get("role") == "admin"):
                return True
        except Exception:
            pass

    # 2. 선택적 환경변수 오버라이드 지원 (배포 환경용)
    admin_emails = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
    admin_users = [u.strip() for u in os.environ.get("ADMIN_USERS", "").split(",") if u.strip()]

    if email_clean and any(email_clean.lower() == adm for adm in admin_emails):
        return True
    if name_clean and any(adm == name_clean for adm in admin_users):
        return True

    return False


def get_user_role(user_or_session):
    """사용자의 시스템 권한 등급을 반환한다 ('admin', 'manager', 'member', 'viewer')."""
    if not user_or_session:
        return "viewer"
    if is_admin_user(user_or_session):
        return "admin"
    if isinstance(user_or_session, dict):
        role = user_or_session.get("role")
        if role in ("admin", "manager", "member", "viewer"):
            return role
        # Query DB
        name = user_or_session.get("name")
        dept = user_or_session.get("org") or user_or_session.get("dept_id")
        if name:
            row = get_one("SELECT role, is_admin FROM users WHERE name = ? AND dept_id = ? LIMIT 1", (name, dept))
            if row:
                if row.get("is_admin"):
                    return "admin"
                return row.get("role") or "member"
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
    - is_private == 1 (비공개/급여/인사): 작성자, 담당자, 부서장(manager), admin만 열람 가능 (타 부서는 차단)
    - manager: 자기 부서 전체 + 타 부서의 일반 공개 레코드 열람 가능
    - member / viewer: 자기 부서 레코드 또는 본인이 담당자/참여자로 지정된 레코드 열람 가능
    """
    if not user_or_session:
        return False
    role = get_user_role(user_or_session)
    if role == "admin":
        return True

    u_name = user_or_session.get("name", "").strip().lower()
    u_dept = (user_or_session.get("org") or user_or_session.get("dept_id") or "").strip().lower()

    rec_dept = (record.get("dept_id") or record.get("org") or "").strip().lower()
    rec_assignee = (record.get("assignee_name") or record.get("assignee") or "").strip().lower()
    rec_participants = (record.get("participants") or "").strip().lower()
    is_private = bool(record.get("is_private"))

    is_involved = (u_name and (u_name in rec_assignee or u_name in rec_participants))
    is_same_dept = (u_dept and u_dept == rec_dept)

    # 비공개 레코드 격리
    if is_private:
        if is_involved:
            return True
        if is_same_dept and role == "manager":
            return True
        return False

    # 일반 레코드
    if is_same_dept:
        return True
    if is_involved:
        return True
    if role == "manager":
        # 타 부서라도 비공개가 아닌 일반 레코드는 협업을 위해 열람 허용
        return True

    return False


def can_modify_record(user_or_session, record):
    """레코드 수정/삭제 권한 판정 (viewer는 읽기 전용으로 차단)"""
    if not user_or_session:
        return False
    role = get_user_role(user_or_session)
    if role == "admin":
        return True
    if role == "viewer":
        return False

    u_name = user_or_session.get("name", "").strip().lower()
    u_dept = (user_or_session.get("org") or user_or_session.get("dept_id") or "").strip().lower()

    rec_dept = (record.get("dept_id") or record.get("org") or "").strip().lower()
    rec_assignee = (record.get("assignee_name") or record.get("assignee") or "").strip().lower()

    if role == "manager" and u_dept == rec_dept:
        return True
    if u_name and u_name in rec_assignee:
        return True

    return False


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
    무차별 대입 공격(Brute-force) 방어:
    동일 IP+사용자 기준 15분 내 5회 이상 로그인 실패 시 임시 잠금 처리.
    """
    now = time.time()
    key = f"{ip}:{(identifier or '').strip().lower()}"
    with _login_failures_lock:
        attempts = [t for t in _login_failures.get(key, []) if now - t < 900]
        _login_failures[key] = attempts
        if len(attempts) >= 5:
            remaining = int(900 - (now - attempts[0]))
            mins = max(1, remaining // 60)
            return False, f"보안 경고: 로그인 시도 실패 횟수 초과로 계정이 임시 잠금되었습니다. {mins}분 후 다시 시도하세요."
        return True, ""

def record_login_failure(ip, identifier):
    """로그인 실패 시각 기록."""
    now = time.time()
    key = f"{ip}:{(identifier or '').strip().lower()}"
    with _login_failures_lock:
        attempts = [t for t in _login_failures.get(key, []) if now - t < 900]
        attempts.append(now)
        _login_failures[key] = attempts

def clear_login_failures(ip, identifier):
    """로그인 성공 시 실패 기록 초기화."""
    key = f"{ip}:{(identifier or '').strip().lower()}"
    with _login_failures_lock:
        if key in _login_failures:
            del _login_failures[key]

def create_session(name, org, email):
    """새 로그인 세션을 생성한다."""
    token = secrets.token_hex(24)
    is_admin = is_admin_user(name, email)
    ts = time.time()

    execute(
        """INSERT INTO sessions(token, user_name, user_dept_id, user_email, is_admin, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (token, name, org, email, 1 if is_admin else 0, ts)
    )
    return token

def get_session(token):
    """토큰으로 세션 정보를 반환한다 (TTL 만료 검증 포함)."""
    if not token:
        return None
    row = get_one(
        "SELECT user_name, user_dept_id, user_email, is_admin, created_at FROM sessions WHERE token = ?",
        (token,)
    )
    if not row:
        return None

    created_at = row.get("created_at") or 0
    now = time.time()
    ttl = get_session_ttl_seconds()

    # Session TTL 만료 검증
    if now - created_at > ttl:
        try:
            execute("DELETE FROM sessions WHERE token = ?", (token,))
        except Exception:
            pass
        return None

    is_admin = bool(row["is_admin"])
    return {
        "name": row["user_name"],
        "org": row["user_dept_id"],
        "email": row["user_email"],
        "isAdmin": is_admin,
        "role": "admin" if is_admin else "member",
        "ts": created_at,
    }

def delete_session(token):
    """단일 세션 만료 (로그아웃)."""
    if token:
        try:
            execute("DELETE FROM sessions WHERE token = ?", (token,))
        except Exception:
            pass

def delete_all_user_sessions(user_name):
    """해당 사용자의 모든 기기 세션 강제 만료 (Logout from all devices)."""
    if user_name:
        try:
            execute("DELETE FROM sessions WHERE user_name = ?", (user_name,))
        except Exception:
            pass

def cleanup_expired_sessions():
    """주기적으로 만료된 세션을 정리한다."""
    cutoff = time.time() - get_session_ttl_seconds()
    try:
        execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
    except Exception:
        pass


