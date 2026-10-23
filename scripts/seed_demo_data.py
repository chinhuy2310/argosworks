"""
seed_demo_data.py — B2B Enterprise Sample Data Generator for ARGOS WORKS

Clears existing test/dirty records and populates realistic, production-grade
sample data for an enterprise B2B deployment:
- 5 Standard Departments (mgmt, dev, sales, hr, hq)
- 8 Standard Corporate Users with realistic Vietnamese executive & staff profiles
  (All demo users have default password: Argos@2026!)
- Realistic Records across all Kanban workflow stages (To Do, In Progress, Review, Done)
- Detailed Comments on tasks showing real cross-department collaboration
- Enterprise PIM Products & Categories (Industrial IoT, Gateways, Software Licenses)
- Schedule & Calendar events with real participant rosters
- Lounge announcements highlighting Local-First & On-Premise security
- Clean Audit Logs recording operational events
- Valid Enterprise License (50 Seats, active through 2029)
"""

import os
import sys
import sqlite3
import hashlib
from datetime import datetime, timedelta

SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server")
sys.path.insert(0, SERVER_DIR)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "argos.db")
PBKDF2_ROUNDS = 600000


def hash_pwd(password: str):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex(), digest.hex()


def run_seed():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF;")  # Disable during clean reset
    cur = conn.cursor()

    print("[1/8] Cleaning up existing transactional and test records...")
    tables_to_clear = [
        "sessions",
        "chat_messages",
        "chat_sessions",
        "record_comments",
        "record_attachments",
        "record_jira",
        "records",
        "schedule_participants",
        "schedule_events",
        "product_attachments",
        "products",
        "product_categories",
        "lounge_messages",
        "notifications",
        "audit_logs",
        "ai_usage",
        "login_attempts",
        "users",
        "card_sequences",
        "departments",
        "license_info"
    ]
    for tbl in tables_to_clear:
        try:
            cur.execute(f"DELETE FROM {tbl};")
        except sqlite3.OperationalError:
            pass

    print("[2/8] Seeding Standard Enterprise Departments...")
    departments = [
        ("mgmt", "Ban Lãnh Đạo & Điều Hành", 1, "MGMT", "MGMT", '["Chiến Lược","Kế Hoạch","Duyệt Chi","Báo Cáo"]'),
        ("dev", "Khối Kỹ Thuật & Trí Tuệ Nhân Tạo", 2, "DEV", "ARGOS", '["Hạ Tầng","Tính Năng","Bảo Mật","Tối Ưu","API"]'),
        ("sales", "Khối Kinh Doanh & Khách Hàng B2B", 3, "SALES", "SALES", '["Hợp Đồng","Khách Hàng","Đối Tác","Đấu Thầu"]'),
        ("hr", "Phòng Nhân Sự & Vận Hành Doanh Nghiệp", 4, "HR", "HR", '["Tuyển Dụng","Đào Tạo","Chính Sách","Văn Hóa"]'),
        ("hq", "Ban Kiểm Soát & Tuân Thủ Nội Bộ", 5, "HQ", "HQ", '["Kiểm Toán","Pháp Lý","SLA","Đánh Giá"]')
    ]
    cur.executemany(
        """INSERT INTO departments (id, name, color_index, local_prefix, jira_key, custom_categories)
           VALUES (?, ?, ?, ?, ?, ?)""",
        departments
    )

    for d in departments:
        cur.execute("INSERT INTO card_sequences (dept_id, last_seq) VALUES (?, 100)", (d[0],))

    print("[3/8] Seeding Enterprise Users (Password: Argos@2026!)...")
    # Generate PBKDF2 hash for Argos@2026!
    salt_hex, hash_hex = hash_pwd("Argos@2026!")
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    users_data = [
        # id, username, name, dept_id, email, is_admin, role, status
        (1, "admin", "Nguyễn Hải Đăng", "mgmt", "dang.nguyen@argosworks.vn", 1, "admin", "active"),
        (2, "quan.tm", "Trần Minh Quân", "dev", "quan.tran@argosworks.vn", 1, "manager", "active"),
        (3, "nam.lh", "Lê Hoàng Nam", "dev", "nam.le@argosworks.vn", 0, "member", "active"),
        (4, "lan.nt", "Nguyễn Thị Mai Lan", "dev", "lan.nguyen@argosworks.vn", 0, "member", "active"),
        (5, "ha.pt", "Phạm Thu Hà", "sales", "ha.pham@argosworks.vn", 0, "manager", "active"),
        (6, "anh.vd", "Vũ Đức Anh", "sales", "anh.vu@argosworks.vn", 0, "member", "active"),
        (7, "linh.ht", "Hoàng Thùy Linh", "hr", "linh.hoang@argosworks.vn", 0, "manager", "active"),
        (8, "duy.pt", "Phan Thanh Duy", "hq", "duy.phan@argosworks.vn", 0, "viewer", "active"),
    ]

    for u in users_data:
        cur.execute(
            """INSERT INTO users (id, username, name, dept_id, email, avatar_url, salt, password_hash,
                                  hash_algo, iterations, is_admin, role, disabled, status, created_at)
               VALUES (?, ?, ?, ?, ?, '', ?, ?, 'pbkdf2_sha256', ?, ?, ?, 0, ?, ?)""",
            (u[0], u[1], u[2], u[3], u[4], salt_hex, hash_hex, PBKDF2_ROUNDS, u[5], u[6], u[7], now_iso)
        )

    print("[4/8] Seeding Realistic B2B Records & Kanban Tasks...")
    base_time = int(datetime.now().timestamp() * 1000)
    today = datetime.now()
    d_m7 = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    d_m3 = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    d_today = today.strftime("%Y-%m-%d")
    d_p3 = (today + timedelta(days=3)).strftime("%Y-%m-%d")
    d_p7 = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    d_p14 = (today + timedelta(days=14)).strftime("%Y-%m-%d")

    records_data = [
        # (id, dept_id, category, title, project, assignee_id, assignee_name, assignee_email, start_date, due_date, status, card_code, priority, memo, jira_key)
        (base_time + 1, "dev", "Hạ Tầng", "Triển khai cụm máy chủ On-Premise & cô lập mạng LAN an toàn",
         "Dự Án Hạ Tầng 2026", 2, "Trần Minh Quân", "quan.tran@argosworks.vn", d_m7, d_m3, "완료", "DEV-101", "긴급",
         "Thiết lập cụm máy chủ vật lý nội bộ chạy Linux Debian LTS, cấu hình mạng DMZ cô lập, bảo đảm 100% dữ liệu không truyền ra ngoài Internet.", "ARGOS-101"),

        (base_time + 2, "dev", "Bảo Mật", "Mã hóa AES-256 at-rest cho kho lưu trữ dữ liệu doanh nghiệp",
         "Dự Án Hạ Tầng 2026", 3, "Lê Hoàng Nam", "nam.le@argosworks.vn", d_m3, d_p3, "진행", "DEV-102", "긴급",
         "Kích hoạt chuẩn mã hóa cơ sở dữ liệu và phân vùng tệp đính kèm với khóa quản lý nội bộ trên thiết bị phần cứng HSM.", "ARGOS-102"),

        (base_time + 3, "dev", "Tính Năng", "Tích hợp mô hình AI LLM nội bộ (Ollama/vLLM) phân tích tài liệu",
         "Argos AI Assistant", 4, "Nguyễn Thị Mai Lan", "lan.nguyen@argosworks.vn", d_m3, d_p7, "진행", "DEV-103", "높음",
         "Triển khai mô hình ngôn ngữ lớn cục bộ chạy trên máy chủ GPU nội bộ. Hỗ trợ hỏi đáp tài liệu, tóm tắt báo cáo tuần mà không cần kết nối đám mây công cộng.", "ARGOS-103"),

        (base_time + 4, "dev", "API", "Đồng bộ 2 chiều Webhook trạng thái công việc với Jira Data Center On-Premise",
         "Argos Connect & Jira", 3, "Lê Hoàng Nam", "nam.le@argosworks.vn", d_today, d_p7, "진행", "DEV-104", "높음",
         "Hoàn thiện module webhook đồng bộ trạng thái ticket Jira với thẻ Kanban trên Argos Works theo thời gian thực.", "ARGOS-104"),

        (base_time + 5, "sales", "Khách Hàng", "Thẩm định kiến trúc Local-First & giải pháp bảo mật cho Tập đoàn Viễn Thông X",
         "Hợp Đồng Chiến Lược Q4", 5, "Phạm Thu Hà", "ha.pham@argosworks.vn", d_m7, d_p3, "진행", "SALES-201", "긴급",
         "Trình bày chi tiết kiến trúc On-Premise, khả năng cách ly hoàn toàn trên mạng nội bộ và tính năng kiểm soát quyền hạn RBAC đa cấp.", "SALES-201"),

        (base_time + 6, "sales", "Đấu Thầu", "Soạn thảo hồ sơ đề xuất & bảng tính TCO bản quyền Enterprise 50 Seats",
         "Hợp Đồng Chiến Lược Q4", 6, "Vũ Đức Anh", "anh.vu@argosworks.vn", d_today, d_p7, "검토", "SALES-202", "보통",
         "Tổng hợp báo giá bản quyền vĩnh viễn, gói bảo trì kỹ thuật 24/7 và đào tạo chuyển giao công nghệ cho 50 người dùng.", "SALES-202"),

        (base_time + 7, "hr", "Tuyển Dụng", "Hoàn tất thủ tục tiếp nhận & cấp thiết bị cho 2 Kỹ sư Phần mềm mới",
         "Vận Hành Nhân Sự Q4", 7, "Hoàng Thùy Linh", "linh.hoang@argosworks.vn", d_m7, d_m3, "완료", "HR-301", "보통",
         "Ký kết hợp đồng lao động, bàn giao máy trạm làm việc và cấp tài khoản đăng nhập hệ thống Argos Works.", "HR-301"),

        (base_time + 8, "hr", "Đào Tạo", "Tổ chức hội thảo nội bộ: Sử dụng AI Assistant an toàn theo chuẩn bảo mật ISO 27001",
         "Vận Hành Nhân Sự Q4", 7, "Hoàng Thùy Linh", "linh.hoang@argosworks.vn", d_today, d_p14, "대기", "HR-302", "보통",
         "Tập huấn cho toàn bộ nhân sự các phòng ban về cách tra cứu kiến thức qua RAG nội bộ và quy định không chia sẻ tài liệu mật.", "HR-302"),

        (base_time + 9, "mgmt", "Chiến Lược", "Phê duyệt kế hoạch ngân sách mở rộng hạ tầng máy chủ AI năm 2027",
         "Kế Hoạch Doanh Nghiệp", 1, "Nguyễn Hải Đăng", "dang.nguyen@argosworks.vn", d_m3, d_p3, "검토", "MGMT-401", "높음",
         "Xem xét tờ trình của Khối Kỹ Thuật về việc đầu tư bổ sung 2 node máy chủ chuyên dụng phục vụ mô hình ngôn ngữ lớn cục bộ.", "MGMT-401"),

        (base_time + 10, "hq", "Kiểm Toán", "Rà soát nhật ký Audit Log & đánh giá tuân thủ phân quyền người dùng",
         "Kiểm Soát Nội Bộ", 8, "Phan Thanh Duy", "duy.phan@argosworks.vn", d_m3, d_p7, "진행", "HQ-501", "높음",
         "Kiểm tra tính toàn vẹn của chuỗi sự kiện kiểm toán, bảo đảm mọi thao tác sửa đổi dữ liệu quan trọng đều được ghi nhận minh bạch.", "HQ-501")
    ]

    for r in records_data:
        cur.execute(
            """INSERT INTO records (id, dept_id, category, title, project, assignee_id, assignee_name,
                                    assignee_email, start_date, due_date, work_date, summary, tags, memo,
                                    status, priority, card_code, participants, parent_key, is_scheduled,
                                    version, is_private, updated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '["Enterprise","B2B"]', ?, ?, ?, ?, '', '', 1, 1, 0, ?, ?)""",
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], f"{r[8]} ~ {r[9]}", r[3],
             r[13], r[10], r[12], r[11], now_iso, now_iso)
        )
        cur.execute(
            """INSERT INTO record_jira (record_id, jira_key, jira_status, jira_url)
               VALUES (?, ?, ?, ?)""",
            (r[0], r[14], "IN_PROGRESS" if r[10] == "진행" else ("DONE" if r[10] == "완료" else "TO_DO"),
             f"https://jira.internal.argosworks.vn/browse/{r[14]}")
        )

    print("[5/8] Seeding Professional Task Comments...")
    comments_data = [
        (base_time + 1, "Trần Minh Quân", "Cụm máy chủ đã nghiệm thu phần cứng, đo kiểm băng thông LAN đạt 10Gbps ổn định.", now_iso),
        (base_time + 2, "Lê Hoàng Nam", "Đã cấu hình master key tại /etc/argos/security/master.key với quyền đọc 600, chỉ daemon root có quyền truy cập.", now_iso),
        (base_time + 3, "Nguyễn Thị Mai Lan", "Mô hình LLM 7B cục bộ chạy với vLLM đạt tốc độ phản hồi 45 tokens/giây, không tiêu tốn băng thông Internet.", now_iso),
        (base_time + 4, "Trần Minh Quân", "Cần bổ sung HMAC-SHA256 signature verification trên endpoint tiếp nhận webhook từ Jira.", now_iso),
        (base_time + 5, "Phạm Thu Hà", "Khách hàng rất hài lòng với mô hình Local-First, vì hoàn toàn giải quyết được lo ngại về an toàn thông tin của ban giám đốc họ.", now_iso),
        (base_time + 9, "Nguyễn Hải Đăng", "Đồng ý chủ trương phê duyệt. Phòng Tài chính chuẩn bị hợp đồng mua sắm theo đúng định mức.", now_iso),
        (base_time + 10, "Phan Thanh Duy", "Qua kiểm tra đối chiếu 1,000 bản ghi audit log gần nhất, toàn bộ thao tác đều khớp với tài khoản người dùng tương ứng.", now_iso)
    ]
    for c in comments_data:
        cur.execute(
            """INSERT INTO record_comments (record_id, author_name, body, created_at)
               VALUES (?, ?, ?, ?)""",
            c
        )

    print("[6/8] Seeding Enterprise PIM Products & Categories...")
    categories = [
        ("cat-iot", "Hệ Thống IoT & Cảm Biến Công Nghiệp", '[{"name":"Giao thức","type":"select","options":["RS485","Modbus","Ethernet"]},{"name":"Cấp bảo vệ","type":"text"}]'),
        ("cat-gw", "Thiết Bị Cổng Kết Nối Biên (Edge Gateway)", '[{"name":"Số cổng LAN","type":"number"},{"name":"Nguồn cấp","type":"text"}]'),
        ("cat-lic", "Bản Quyền Phần Mềm On-Premise", '[{"name":"Số lượng Seats","type":"number"},{"name":"Thời hạn","type":"text"}]'),
        ("cat-ai", "Thiết Bị Xử Lý Trí Tuệ Nhân Tạo Biên", '[{"name":"Công suất tính toán","type":"text"},{"name":"NPU TOPS","type":"number"}]')
    ]
    cur.executemany("INSERT INTO product_categories (id, name, spec_template, created_at) VALUES (?, ?, ?, ?)",
                    [(c[0], c[1], c[2], now_iso) for c in categories])

    products_data = [
        ("ARGOS-IOT-S300", "ARGOS-IOT-S300", "Cảm Biến Giám Sát Nhiệt Độ & Rung Chấn Công Nghiệp S300", "Họ Cảm Biến S-Series",
         "판매 중", "Hệ Thống IoT & Cảm Biến Công Nghiệp", "Cảm biến công nghiệp đạt chuẩn IP68 đo nhiệt độ và rung chấn máy móc",
         "Giao thức Modbus RTU / RS485, dải nhiệt độ -40°C đến 125°C",
         '{"Giao thức":"Modbus-RTU","Cấp bảo vệ":"IP68","Dải đo":"-40°C đến 125°C"}',
         8500000, "VND", "internal"),

        ("ARGOS-GW-EDGE2", "ARGOS-GW-EDGE2", "Bộ Cổng Gateway Công Nghiệp 4 Cổng Cách Ly Quang Edge-V2", "Họ Gateway Edge",
         "판매 중", "Thiết Bị Cổng Kết Nối Biên (Edge Gateway)", "Gateway truyền thông công nghiệp hỗ trợ mạng kép LAN/WAN cách ly",
         "Nguồn đôi dự phòng 12-24V DC, vỏ nhôm công nghiệp tản nhiệt tự nhiên",
         '{"Số cổng LAN":4,"Nguồn cấp":"12-24V DC","Vỏ máy":"Nhôm nguyên khối"}',
         16800000, "VND", "internal"),

        ("ARGOS-AI-BOX1", "ARGOS-AI-BOX1", "Thiết Bị Phân Tích AI Biên Công Nghiệp Argos Vision Box", "Họ AI Vision",
         "판매 중", "Thiết Bị Xử Lý Trí Tuệ Nhân Tạo Biên", "Thiết bị biên xử lý thị giác máy tính và phân tích dữ liệu cảm biến thời gian thực",
         "32 TOPS NPU, RAM 16GB ECC, hỗ trợ chuẩn ONNX và TensorRT",
         '{"Công suất tính toán":"32 TOPS","Bộ nhớ":"16GB ECC","HĐH":"Argos Linux Core"}',
         32500000, "VND", "internal"),

        ("ARGOS-LIC-ENT50", "ARGOS-LIC-ENT50", "Gói Bản Quyền Nền Tảng Argos Works Enterprise (50 Seats On-Premise)", "Phần Mềm Quản Trị",
         "판매 중", "Bản Quyền Phần Mềm On-Premise", "Bản quyền vĩnh viễn hệ điều hành vận hành Argos Works dành cho 50 người dùng",
         "Bao gồm phân hệ Canvas, PIM, RAG AI, Jira Sync và Audit Log tuân thủ ISO",
         '{"Số lượng Seats":50,"Thời hạn":"Vĩnh viễn","Hỗ trợ kỹ thuật":"12 tháng"}',
         150000000, "VND", "internal")
    ]
    cur.executemany(
        """INSERT INTO products (id, model, display_name, family, lifecycle, category, summary, memo, specs, price, currency, revision, created_at, updated_at, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
        [(p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], p[10], now_iso, now_iso, p[11]) for p in products_data]
    )

    print("[7/8] Seeding Corporate Schedules & Lounge Announcements...")
    schedules = [
        (base_time + 101, 1, "Nguyễn Hải Đăng", "mgmt", "dang.nguyen@argosworks.vn", "meeting",
         "Họp Giao Ban Điều Hành Tuần Mới (Executive Weekly Sync)",
         f"{d_today} 09:00", f"{d_today} 10:30", "Đánh giá tiến độ dự án trọng điểm và chỉ số vận hành các khối phòng ban."),
        (base_time + 102, 2, "Trần Minh Quân", "dev", "quan.tran@argosworks.vn", "sprint",
         "Sprint Review: Kiểm Thử Đồng Bộ Jira On-Premise & Mô Hình AI Cục Bộ",
         f"{d_p3} 14:00", f"{d_p3} 15:30", "Trình chiếu tính năng webhook 2 chiều với Jira và tốc độ phân tích RAG nội bộ."),
        (base_time + 103, 5, "Phạm Thu Hà", "sales", "ha.pham@argosworks.vn", "client",
         "Phiên Thuyết Trình Giải Pháp Local-First Cho Khách Hàng Doanh Nghiệp",
         f"{d_p7} 10:00", f"{d_p7} 11:30", "Demo kiến trúc bảo mật cách ly mạng LAN và cơ chế phân quyền RBAC 4 cấp.")
    ]
    cur.executemany(
        """INSERT INTO schedule_events (id, owner_id, owner_name, owner_dept_id, owner_email, type, title, start_date, end_date, memo, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], now_iso) for s in schedules]
    )
    for s in schedules:
        cur.execute(
            """INSERT INTO schedule_participants (event_id, user_name, user_dept_id, user_email, is_owner)
               VALUES (?, ?, ?, ?, 1)""",
            (s[0], s[2], s[3], s[4])
        )

    lounge_msgs = [
        (base_time + 201, "general", "Nguyễn Hải Đăng", "mgmt", "Tất cả thành viên", "all",
         "Chào mừng toàn thể đội ngũ đến với nền tảng điều hành Argos Works phiên bản 2026. Chúc mọi người một tuần làm việc hiệu quả và bứt phá!", now_iso),
        (base_time + 202, "general", "Trần Minh Quân", "dev", "Tất cả thành viên", "all",
         "Thông báo bảo mật: Cụm máy chủ On-Premise và dịch vụ AI nội bộ đang hoạt động ở trạng thái tối ưu nhất. Toàn bộ tài liệu doanh nghiệp được mã hóa an toàn trong mạng nội bộ.", now_iso),
        (base_time + 203, "general", "Phạm Thu Hà", "sales", "Tất cả thành viên", "all",
         "Tin vui: Đối tác khách hàng B2B đánh giá rất cao giao diện trực quan và tính năng đồng bộ 2 chiều với Jira trong buổi làm việc sáng nay.", now_iso)
    ]
    cur.executemany(
        """INSERT INTO lounge_messages (id, conversation_key, from_name, from_dept_id, to_name, to_dept_id, text, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        lounge_msgs
    )

    print("[8/8] Seeding Enterprise License & Initial Audit Logs...")
    cur.execute(
        """INSERT INTO license_info (id, customer_name, license_key, max_seats, expiry_date, modules_json, is_active, updated_at)
           VALUES (1, 'Argos Enterprise Solutions Corp', 'ARGOS-ENT-2026-LOCAL-B2B', 50, '2029-12-31',
                   '[\"canvas\",\"rag\",\"jira\",\"pim\",\"schedule\",\"audit\"]', 1, ?)""",
        (now_iso,)
    )

    audit_logs = [
        (now_iso, "system", "SYSTEM_BOOTSTRAP", "database", "1", '{"action":"clean_seed","architecture":"local_first_b2b"}'),
        (now_iso, "admin", "LICENSE_ACTIVATED", "license", "1", '{"seats":50,"type":"enterprise_local"}'),
        (now_iso, "admin", "ORGANIZATION_SETUP", "departments", "5", '{"departments":["mgmt","dev","sales","hr","hq"]}'),
        (now_iso, "admin", "USER_MANAGEMENT", "users", "8", '{"status":"active","roles":["admin","manager","member","viewer"]}')
    ]
    cur.executemany(
        """INSERT INTO audit_logs (timestamp, username, action, target_type, target_id, details_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        audit_logs
    )

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()
    print(">>> Seed completed successfully! All enterprise sample data is ready.")


if __name__ == "__main__":
    run_seed()
