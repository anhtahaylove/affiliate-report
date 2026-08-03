# TikTok Affiliate Report

Web app local cho Windows để import Excel export từ TikTok Affiliate, chống double-count khi file bị overlap và theo dõi hiệu suất theo từng affiliate account. UI production là **Next.js Operations Cockpit**; Python/FastAPI giữ toàn bộ parser, dedupe, versioning và công thức báo cáo.

## Chức năng

- Parser đúng 47 cột TikTok; giữ ID dạng text và raw JSON để audit.
- Giới hạn upload 20 MB và 50.000 dòng/file.
- Dedupe file bằng SHA-256; versioning theo `account + order_id + sku_id` khi dữ liệu thay đổi.
- Dashboard `ALL` và từng account: đơn hàng, GMV, hoa hồng, huỷ, KPI ngày/tháng.
- Sửa KPI/ngày theo từng account; owner sửa thêm target tổng `ALL`.
- Upload `.xlsx`, phản hồi duplicate/inserted/updated/unchanged/rejected và lịch sử import gần nhất.
- Roles `owner` / `operator` / `viewer`, account allowlist, OIDC session + CSRF cho shared web.
- SQLite cho local single-user; PostgreSQL cho shared multi-user.
- PWA responsive dùng chung cho web/desktop, sẵn boundary để bọc mobile sau này.

## Cài và chạy trên máy Windows không cần Python

Khi release `v1.1.0` được phát hành, tải installer từ [GitHub Releases](https://github.com/anhtahaylove/tiktok-affiliate-report/releases), đối chiếu `SHA256SUMS.txt`, rồi chạy `TikTokAffiliateReportSetup-v1.1.0.exe`.

Installer cài theo user vào `%LOCALAPPDATA%\TikTokAffiliateReport`, tạo shortcut Desktop/Start Menu. Double-click app sẽ:

1. khởi động FastAPI trên một cổng loopback còn trống;
2. phục vụ Next.js đã bundle cùng EXE;
3. tự mở `http://127.0.0.1:<port>` trong trình duyệt.

Máy người dùng không cần Python, Node.js, pnpm, Docker hoặc Railway. Dữ liệu nằm tại `%LOCALAPPDATA%\TikTokAffiliateReport\data\tiktok_affiliate_report.db` và không được nhúng vào EXE hay ghi đè khi nâng cấp.

Artifact hiện cố ý **không code-sign**; Windows SmartScreen có thể cảnh báo. SHA-256 xác minh integrity, không thay thế publisher trust.

## Chạy source trên Windows

Yêu cầu cho máy phát triển: Python 3.11+, Node.js 22 và pnpm.

```powershell
corepack enable
.\START_REPORT.bat
```

Launcher tự tạo `.venv`, cài `requirements-api.txt`, build `web/out` khi thiếu rồi mở app. Kiểm tra nhanh không chạy server:

```powershell
.\START_REPORT.bat --check
```

## Chạy API và Next.js riêng khi phát triển

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe run_api.py
```

Terminal khác:

```powershell
Copy-Item web\.env.example web\.env.local
pnpm --dir web install --frozen-lockfile
pnpm --dir web dev
```

Mở `http://127.0.0.1:3000`; API local ở `http://127.0.0.1:8000`. `AUTH_MODE=local` chỉ được bind loopback và dùng local owner.

## Shared web với OIDC + PostgreSQL

Shared multi-user cần PostgreSQL, OIDC provider thật, TLS/reverse proxy và secret injection ngoài Git:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://app:<PASSWORD>@127.0.0.1:5432/tiktok_affiliate_report'
$env:AUTH_MODE = 'oidc'
$env:OIDC_ISSUER = 'https://id.example.com'
$env:OIDC_CLIENT_ID = '<CLIENT_ID>'
$env:OIDC_CLIENT_SECRET = '<CLIENT_SECRET>'
$env:OIDC_REDIRECT_URI = 'https://report.example.com/auth/callback'
$env:AUTH_BOOTSTRAP_OWNER_EMAIL = 'owner@example.com'
$env:AUTH_ALLOWED_EMAILS = 'owner@example.com,user@example.com'
$env:WEB_APP_URL = 'https://report.example.com'
$env:API_CORS_ORIGINS = 'https://report.example.com'
$env:API_HOST = '0.0.0.0'
.\.venv\Scripts\python.exe run_api.py
```

`AUTH_DEFAULT_ACCOUNTS` mặc định rỗng. User mới chỉ thấy account sau khi owner cấp quyền qua API quản trị. Không commit client secret hoặc database password.

Chuyển database SQLite local sang PostgreSQL rỗng:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py `
  --source data\tiktok_affiliate_report.db `
  --target 'postgresql+psycopg://app:<PASSWORD>@127.0.0.1:5432/tiktok_affiliate_report'
```

Tool copy dữ liệu nghiệp vụ và user/account mapping, không copy session/OIDC state, rồi kiểm tra row counts và PostgreSQL sequences.

## Build EXE và installer

```powershell
.\BUILD_EXE.bat
.\packaging\build_installer.ps1 -SkipAppBuild
```

Output:

- `dist\TikTokAffiliateReport.exe`
- `artifacts\installer\TikTokAffiliateReportSetup-v1.1.0.exe`
- `artifacts\installer\SHA256SUMS.txt`

`BUILD_EXE.bat` build static Next.js, bundle FastAPI + web assets, rồi chạy privacy gate để chặn database người dùng lọt vào artifact. Build installer cần Inno Setup 6 trên máy phát triển:

```powershell
winget install --id JRSoftware.InnoSetup --exact
```

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q tiktok_affiliate_report scripts tests desktop_launcher.py
.\.venv\Scripts\python.exe -m pip check
pnpm --dir web lint
pnpm --dir web build
git diff --check
```

## Tài liệu

- [PRD](docs/PRD-TikTok-Affiliate-Report.md)
- [Input/output mapping](docs/DATA_MAPPING.md)
- [Database schema](docs/schema.sql)
- [Phase 2 architecture](docs/PHASE-2-ARCHITECTURE.md)

## Quy tắc dữ liệu

- File TikTok không chứa tên affiliate account sở hữu file; `Tên cửa hàng` là seller shop. Người upload phải chọn account, app không suy account từ filename.
- Không dedupe chỉ bằng `ID đơn hàng`: một order có thể có nhiều SKU.
- `Tổng số tiền nhận được cuối cùng` là KPI TikTok riêng, không phải `Hoa hồng thực tế` theo workbook.
- Một dòng không xuất hiện trong file sau không bị xem là đã xoá.
- `target_commission` trong database/API là **KPI hoa hồng mỗi ngày**, không phải tổng target tháng.
- `REPORT AFF.xlsx` là nguồn thiết kế output legacy; app không cần link Google Sheets để chạy.
