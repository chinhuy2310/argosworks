# ARGOS WORKS — Danh mục chỉnh sửa để thành sản phẩm thương mại

Tài liệu này liệt kê **các hạng mục cần sửa** để ARGOS WORKS có thể bán cho công ty / doanh nghiệp (on-premise).  
Trạng thái hiện tại: **MVP nội bộ / demo** — chưa phải commercial product hoàn chỉnh.

Cách dùng: tick từng mục khi hoàn thành. Ưu tiên **P0 → P1 → P2**. Không bắt đầu P2 khi P0 còn mở.

---

## 0. Định hướng (không đổi kiến trúc cốt lõi)

- [ ] Giữ mô hình **on-premise, 1 khách = 1 instance**. Không chuyển SaaS đa tenant ở giai đoạn đầu.
- [ ] Bán như **lớp tri thức + bàn giao kỹ thuật** (canvas, RAG, lịch, PIM), **không** bán như thay thế Jira.
- [ ] Tách rõ **bản nguồn nội bộ** và **bản giao khách** (không dính dữ liệu / connector / alias của một công ty).

---

## P0 — Chặn ký hợp đồng / không được đưa vào mạng khách (ĐÃ HOÀN THÀNH 100%)

### P0.1 Bảo mật API và phiên đăng nhập

- [x] Bắt buộc đăng nhập cho **mọi** `/api/*` trừ health check và login/register (register sẽ tắt — xem P0.2).
- [x] Khóa các endpoint hiện đang đọc công khai:
  - `/api/records`, `/api/records/hierarchy`
  - `/api/members`, `/api/departments`, `/api/categories`
  - `/api/products`, `/api/products/detail`, `/api/products/attachment`
  - `/api/ask`
  - `/api/schedule`
  - `/api/attachments/*`, `/api/jira/attachments/*`
  - `/api/issues*`
  - `/api/notifications*` (không cho đọc/đánh dấu đã đọc khi chưa login; kiểm tra đúng chủ sở hữu)
  - `/api/vectors/stats`
- [x] Session có **TTL thật** (đề xuất 8–24 giờ), không chỉ cookie `Max-Age=30 ngày` (Mặc định 24h, cấu hình qua `SESSION_TTL_HOURS`).
- [x] `get_session()` từ chối token hết hạn; dọn session cũ (Tự động xóa session hết hạn khi truy cập và chạy background thread hàng giờ).
- [x] Logout xóa session server-side (đã có) + cookie; thêm **logout mọi thiết bị** (`POST /api/account/logout-all`).
- [x] Rate-limit + khóa tạm tài khoản khi login sai nhiều lần (theo IP và theo user: khóa 15 phút sau 5 lần thử sai).
- [x] CSRF token / SameSite=Lax/Strict + HttpOnly + Secure headers phòng chống XSS & F12 token theft.
- [x] Không trả raw exception ra client (`handler.py` ẩn traceback `str(e)` ở HTTP 500, log nội bộ tại server).

### P0.2 Tài khoản và mật khẩu

- [x] **Tắt tự đăng ký** mặc định (`/api/account/register`). Chỉ admin tạo / mời user.
- [x] Cờ cấu hình `ALLOW_PUBLIC_REGISTER=false` (chỉ bật cho demo có kiểm soát).
- [x] Policy mật khẩu: tối thiểu 8 ký tự, từ chối mật khẩu ngắn dưới 8 ký tự.
- [x] Không tự phong admin cho user đầu theo cách khó kiểm soát; phân quyền admin rõ ràng trong DB (`users.is_admin`).
- [x] Vô hiệu hóa / khóa user (disable) mà không xóa dữ liệu lịch sử (`acc.get("disabled")`).

### P0.3 Bí mật, cấu hình, git

- [x] Không lưu API key plaintext trong `server/config.json`.
- [x] Chỉ dùng `.env` (hoặc secret store); `config.json` chỉ còn giá trị không nhạy cảm.
- [x] Thêm `.gitignore`: `.env`, `data/*.db`, `data/*.sqlite`, `logs/`, backup, `server/config.json` nếu chứa secret.
- [x] Thêm `.env.example` đủ field, không có giá trị thật.
- [x] **Rotate** mọi key AI / Jira / embedding đã từng nằm trong repo hoặc máy demo.
- [x] Không commit DB, vector store, chat history, attachments vào git.

### P0.4 Tách “bản một công ty” khỏi sản phẩm

- [x] Xóa / chuyển `NAME_ALIASES` nhân sự cứng trong `router.py` thành đối chiếu động từ bảng tài khoản hệ thống.
- [x] Đưa connector Vision119 ra module **tùy chọn**, tắt mặc định trên bản giao khách.
- [x] `config.json` / seed không chứa URL Jira, email, project key của cá nhân / nội bộ.
- [x] Đổi branding còn sót: `JarvisHandler` → `ArgosHandler`, log “JARVIS” → “Argos”, `server_version` → `ArgosServer/2.0`.
- [x] Bản giao khách: DB độc lập, không hardcode danh sách người của một công ty duy nhất.

### P0.5 Pháp lý tối thiểu

- [x] `LICENSE` (mã nguồn nội bộ / giấy phép thương mại) + **EULA** cho khách on-prem (`docs/EULA.md`).
- [x] Điều khoản xử lý dữ liệu (DPA) / cam kết 100% dữ liệu nằm tại máy khách.
- [x] Chính sách backup, lưu trữ, xóa dữ liệu khi hết hợp đồng.
- [x] Không thu thập telemetry mặc định; nếu có thì opt-in (Zero Default Telemetry).

---

## P1 — Doanh nghiệp sẽ hỏi trong POC

### P1.1 Phân quyền (RBAC)

- [ ] Nhiều hơn `admin` / `member`:
  - `admin` — hệ thống, user, backup, settings
  - `dept_admin` — quản lý phòng mình
  - `member` — tạo/sửa việc được giao hoặc phòng mình
  - `viewer` — chỉ đọc
- [ ] Kiểm tra quyền **phía server** (không chỉ ẩn tab UI).
- [ ] Phân tách dữ liệu theo phòng: member không đọc toàn bộ công ty nếu policy không cho.
- [ ] PIM / SPEC: quyền xem giá, tài liệu firmware riêng (thường là admin / phòng kinh doanh).

### P1.2 Đăng nhập doanh nghiệp

- [ ] SSO: OIDC (Google Workspace / Azure AD / Keycloak).
- [ ] Tùy chọn LDAP / Active Directory (nhiều nhà máy vẫn dùng).
- [ ] MFA cho tài khoản admin (TOTP).
- [ ] Invite bằng email hoặc mã một lần nếu không có SSO.

### P1.3 Audit và tuân thủ

- [ ] Nhật ký kiểm toán: login, thất bại login, tạo/sửa/xóa record, đổi quyền, backup/restore, đổi settings.
- [ ] Audit không ghi mật khẩu / API key.
- [ ] Xuất audit (CSV/JSON) theo khoảng ngày — phục vụ ISO / kiểm toán nội bộ.
- [ ] Giữ access log hiện tại nhưng **không** dùng làm audit duy nhất.

### P1.4 Vận hành và tải

- [ ] Xác định ngưỡng: SQLite + `ThreadingHTTPServer` chấp nhận được cho ~20–30 user đồng thời.
- [ ] Trên ngưỡng: tùy chọn PostgreSQL + server WSGI/ASGI (gunicorn/uvicorn) sau reverse proxy.
- [ ] Health check không lộ phiên bản / cấu hình nhạy cảm.
- [ ] Header bảo mật trên **cả** Python server (không chỉ Caddy): HSTS khi HTTPS, `X-Content-Type-Options`, `X-Frame-Options` / CSP, `Referrer-Policy`.
- [ ] Giới hạn kích thước body + timeout + số request đồng thời.
- [ ] Backup restore: test định kỳ; tài liệu restore khi sự cố; không restore đè mà không xác nhận admin.
- [ ] Windows Service + systemd unit (không chỉ `.bat` / Docker).

### P1.5 Mã hóa và thư viện

- [ ] Ngừng AES tự viết trong `crypto.py` cho reviewer bảo mật; dùng thư viện chuẩn (hoặc OS keyring / Fernet đã audit).
- [ ] `requirements.txt` pin phiên bản; ghi rõ không còn “zero dependency” nếu đã dùng openpyxl/pillow.
- [ ] Quét dependency (CVE) trước mỗi bản phát hành.

### P1.6 Kiểm thử

- [ ] Test tự động: login, register tắt, API 401 khi chưa login, RBAC 403, backup/restore.
- [ ] Test không lộ secret trong response settings (mask key).
- [ ] CI tối thiểu trên mỗi tag phát hành.

---

## P2 — Đóng gói để bán (productization)

### P2.1 Cài đặt và onboarding

- [ ] Wizard lần đầu: domain, tạo admin, tắt public register, đường dẫn data/backup, chọn nhà cung cấp AI (cloud key **hoặc** Ollama nội bộ).
- [ ] Tài liệu IT (~10 trang): Docker, HTTPS, backup, firewall, nâng cấp.
- [ ] Tài liệu user: đăng nhập, tạo việc, canvas, lịch, hỏi AI.
- [ ] Môi trường demo tách biệt, dữ liệu giả, không dính production.

### P2.2 Giấy phép phần mềm

- [ ] License key: tên công ty, số ghế, ngày hết hạn, module (Jira, AI cloud, PIM).
- [ ] Admin UI hiện trạng thái license.
- [ ] Chặn tạo user khi vượt số ghế.
- [ ] Kích hoạt **offline** (nhà máy không internet).
- [ ] Cảnh báo trước ngày hết hạn; chế độ chỉ-đọc khi hết hạn (không khóa dữ liệu khách).

### P2.3 White-label và i18n

- [ ] Workspace name / logo / footer (đã có mầm) — hoàn thiện trên login + PDF/Excel.
- [ ] i18n **tiếng Việt đầy đủ** (hiện KO/EN; UI/backend còn nhiều chuỗi tiếng Hàn cứng).
- [ ] Chuẩn hóa status (`진행` / Done…) thành mã nội bộ + nhãn theo ngôn ngữ.

### P2.4 Nâng cấp và hỗ trợ

- [ ] Semver (`1.0.0`), CHANGELOG, ghi chú breaking change.
- [ ] Migration `schema.sql` an toàn, không xóa data khi nâng cấp.
- [ ] Gói patch; rollback từ backup.
- [ ] Kênh hỗ trợ: email / ticket, thời gian phản hồi (SLA) theo gói.
- [ ] Không ghi đè thư mục `data/` khi update image/binary.

### P2.5 AI / RAG sản phẩm hóa

- [ ] Air-gap chính thức: Ollama (LLM + embedding) không bắt buộc gọi cloud.
- [ ] Cảnh báo khách khi dữ liệu nội bộ được gửi lên Gemini/OpenAI (opt-in, ghi trong EULA).
- [ ] Giới hạn chi phí / timeout / kích thước context.
- [ ] Công cụ agent không thực thi hành động nhạy cảm (xóa, đổi trạng thái hàng loạt) nếu user không đủ quyền.

---

## P3 — Tập đoàn / vòng bảo mật lớn (sau khi đã bán được SME)

- [ ] Pentest bên thứ ba + vá finding trước GA.
- [ ] Tùy chọn PostgreSQL HA, backup offsite.
- [ ] SAML đầy đủ, SCIM provisioning user.
- [ ] Phân loại dữ liệu (nội bộ / mật / đối tác).
- [ ] Retention policy (xóa tự động chat / log sau N ngày).
- [ ] SOC2 / ISO 27001 (nếu bán thị trường US/EU hoặc tập đoàn lớn).
- [ ] Portal khách: ticket, download bản vá, license.

---

## Thứ tự thực hiện đề xuất

| Pha | Thời gian ước lượng | Mục tiêu |
|---|---|---|
| **1. Khóa an toàn** | 2–3 tuần | Hết P0: auth API, tắt register, session, rate-limit, gitignore, rotate key, ẩn exception, tách data nội bộ |
| **2. Gói SME** | 4–6 tuần | P1 RBAC + audit + P2 installer/license/tài liệu |
| **3. Doanh nghiệp** | 8–12 tuần | SSO, MFA, PostgreSQL option, pentest, EULA/DPA, Ollama air-gap |
| **4. Mở rộng** | Liên tục | i18n VI, connector tùy chọn, portal, HA |

---

## File / module cần đụng trước (Pha 1)

| Khu vực | File chính | Việc |
|---|---|---|
| Auth bắt buộc | `server/handler.py`, `server/router.py` | Middleware 401 cho GET/POST API |
| Đăng ký / mật khẩu | `server/handlers/auth_handlers.py` | Tắt register, policy mật khẩu |
| Session TTL | `server/services/auth.py` | Kiểm hạn, revoke |
| Lỗi 500 | `server/handler.py` | Không leak `str(e)` |
| Secret | `server/config.json`, `server/config.py`, `.gitignore` | Đưa key ra `.env` |
| Hard-code nội bộ | `server/router.py` (NAME_ALIASES), PIM Vision119 | Cấu hình / tắt mặc định |
| Cookie / header | `server/handler.py`, `Caddyfile` | TTL, CSP, HSTS |
| Backup | `server/services/backup_manager.py` | Xác nhận restore, không lộ path |

---

## Tiêu chí “đủ để bán gói SME”

Chỉ coi là **commercial SME** khi:

1. Người lạ trong LAN **không** đọc được records/PIM khi chưa login.
2. Không tự tạo được tài khoản trên bản production.
3. Admin mời user, có số ghế license.
4. Cài được bằng Docker hoặc service, có HTTPS, backup/restore đã test.
5. Bản giao **không** chứa data, key, alias, connector của công ty gốc.
6. Có EULA + hướng dẫn IT.
7. Nâng cấp không làm mất SQLite / attachments.

Chưa cần SSO/PostgreSQL để bán team 10–40 người; **bắt buộc** có các mục P0.
