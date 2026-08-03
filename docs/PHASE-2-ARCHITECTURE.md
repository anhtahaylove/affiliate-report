# Phase 2 Architecture — Python API + Next.js PWA

## 1. Quyết định

Phase 2 không viết lại business logic. Hệ thống giữ một Python core, thêm một HTTP API versioned và dùng Next.js PWA làm UI chung:

```text
Browser / Tauri / Capacitor
            |
       Next.js PWA
            |
      Python API /api/v1
            |
 parser + ingest + reports
            |
 SQLite local / Postgres shared
```

- Streamlit tiếp tục là bản desktop local ổn định trong thời gian chuyển đổi.
- Tauri và Capacitor chỉ là wrapper, không chứa công thức KPI hoặc logic dedupe.
- Expo/React Native chỉ được chọn nếu mobile-first, offline, push notification hoặc native UX trở thành yêu cầu chính.

## 2. Boundary bắt buộc

### Python core

Sở hữu:

- xác thực 47 header TikTok;
- normalization, `business_key`, `normalized_hash`;
- dedupe file và versioning order line;
- current-row selection;
- công thức report/KPI.

Core không biết HTTP, React, phiên đăng nhập hoặc state giao diện.

### Python API

Sở hữu:

- request validation và response shaping;
- upload orchestration;
- filter, search và pagination;
- auth/authorization khi bước OIDC được bật;
- audit identity và error mapping.

API phải gọi `parser.py`, `db.py`, `reports.py`; không được viết lại công thức.

### Next.js PWA

Sở hữu render, filter, upload UI, navigation, responsive behavior và app-shell cache. PWA không đọc database trực tiếp và không tự tính lại KPI.

## 3. Trạng thái triển khai

Python:

- `tiktok_affiliate_report/api.py`
- `run_api.py`
- `requirements-api.txt`
- `tests/test_api.py`

Web:

- `web/src/app`
- `web/src/components/dashboard.tsx`
- `web/src/lib/api.ts`
- `web/public/sw.js`

Gate B đã bổ sung OIDC Authorization Code + PKCE, signed ID-token validation, opaque server-side session, CSRF, roles/account allowlist, PostgreSQL và CI Postgres 16. `AUTH_MODE=local` vẫn tương thích desktop nhưng chỉ được bind loopback; host public/LAN bắt buộc `AUTH_MODE=oidc`.

## 4. API contract hiện tại

Base path: `/api/v1`. Date dùng `YYYY-MM-DD`; tiền là integer VND; null được giữ là JSON `null`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Local readiness |
| GET | `/api/v1/meta` | Accounts, statuses, upload limit |
| GET | `/api/v1/overview` | Summary theo account và `ALL` |
| GET | `/api/v1/daily` | Báo cáo ngày |
| GET | `/api/v1/monthly-kpi` | KPI tháng |
| GET | `/api/v1/orders` | Order explorer có limit/offset |
| POST | `/api/v1/imports` | Multipart `.xlsx` + account bắt buộc |
| GET | `/auth/login`, `/auth/callback`, `/auth/me` | OIDC/session lifecycle |
| POST | `/auth/logout` | Revoke session; yêu cầu CSRF trong OIDC mode |
| GET/PATCH | `/api/v1/admin/users` | Owner quản lý role/account access |

Report response:

```json
{"items": [], "count": 0}
```

Orders response thêm `total`, `limit`, `offset`. Import response giữ `batch_id`, `duplicate`, `inserted`, `updated`, `unchanged`, `rejected`, `rejected_rows`.

## 5. Security target trước khi public web

- OIDC Authorization Code + PKCE.
- Session trong secure, `httpOnly`, `sameSite` cookie; không lưu token ở `localStorage`.
- Roles tối thiểu: `owner`, `operator`, `viewer`.
- Account allowlist được enforce trong API cho cả read và upload.
- CORS chỉ cho origin đã cấu hình; CSRF protection nếu dùng cookie session.
- Rate limit upload, giới hạn 20 MB/50.000 dòng và audit subject/file hash.
- Không log token, cookie hoặc nội dung Excel nhạy cảm.

OIDC là provider-neutral và cấu hình bằng issuer/metadata, client credentials, redirect URI và email allowlist. Deployment thật vẫn cần TLS/reverse proxy, OIDC client hợp lệ, secret injection ngoài Git, PostgreSQL backup và restore drill.

## 6. Data strategy

- SQLite tiếp tục dùng cho local, test và desktop single-user.
- Khi có shared web/multi-user, chuyển canonical store sang Postgres qua cùng SQLAlchemy boundary.
- Browser không có DB credentials.
- Mặc định lưu normalized rows, raw row JSON và file hash; chỉ lưu file Excel gốc nếu có yêu cầu audit/compliance.
- Shared production cần backup định kỳ và restore drill; SQLite chỉ copy khi app đã dừng.

## 7. Migration plan

### Gate A — Parity foundation

- Current Python tests và golden export fixtures pass.
- API output khớp Streamlit cho overview, daily, monthly KPI, orders và duplicate import.

### Gate B — OIDC + Postgres

- **Đã triển khai trong code:** provider discovery, ID-token/issuer/nonce validation, session/CSRF, user/role/account mapping, PostgreSQL data layer và migration CI.
- **Deployment input còn thiếu:** issuer/client credentials thật, DNS/TLS và database PostgreSQL đích.

### Gate C — Next.js feature parity

- Upload, filters, KPI, daily, orders, import history và exports có đủ trên PWA.
- Không có business math trong TypeScript.
- PWA installable; app shell hoạt động offline, report data yêu cầu API.

### Gate D — Wrappers

- Tauri đóng gói cùng web build cho desktop.
- Capacitor đóng gói cùng web build cho Android/iOS.
- Native plugins chỉ cho file picker/share/deep link/notification; không duplicate domain logic.

### Gate E — Streamlit deprecation

Chỉ deprecate khi PWA đạt parity, migration/rollback được thử và người dùng hiện tại chuyển đổi thành công.

## 8. Acceptance criteria

- Duplicate file vẫn là no-op.
- Overlap chỉ tạo version mới khi normalized content thay đổi.
- Upload luôn yêu cầu account rõ ràng.
- Report/KPI API khớp Python core.
- Missing import không bị đổi thành số 0.
- Mọi endpoint ngoài health được auth trước khi public.
- Web, desktop và mobile dùng cùng API contract và cùng PWA surface.
- Wrapper không có business rule riêng.

## 9. Rủi ro và cách chặn

| Risk | Gate |
| --- | --- |
| Logic Python/TypeScript lệch nhau | Cấm công thức KPI trong frontend; parity tests |
| Public API chạy nhầm local auth | `run_api.py` từ chối non-loopback nếu không phải OIDC |
| SQLite concurrency | Chuyển Postgres trước shared multi-user |
| Wrapper sprawl | Wrapper chỉ packaging/native bridge |
| Offline scope quá lớn | Chỉ cache app shell trước; data sync khi có yêu cầu thật |

## 10. Lệnh local

```powershell
python -m pip install -r requirements-api.txt
python run_api.py
```

```powershell
Set-Location web
Copy-Item .env.example .env.local
pnpm install
pnpm dev
```
