# TikTok Affiliate Report

Ứng dụng Streamlit chạy local trên Windows để upload Excel export từ TikTok Affiliate, chống double-count khi các lần export bị overlap, giữ lịch sử version theo dòng `account + order_id + sku_id` và dựng dashboard theo logic `REPORT AFF.xlsx`.

## Chức năng hiện có

- Parser đúng 47 cột TikTok; giữ ID dạng text và raw JSON để audit.
- Giới hạn upload 20 MB và 50.000 dòng/file.
- Dedupe file bằng SHA-256; versioning khi cùng order/SKU đổi dữ liệu.
- Tổng quan theo account và hàng tổng `ALL`.
- Báo cáo ngày/tháng, KPI, đơn hàng hiện hành và lịch sử import.
- Output wide tải CSV để dán/import vào Google Sheets.
- Migration có version; dữ liệu local lưu bằng SQLite tại `data/tiktok_affiliate_report.db`.
- Chạy bằng launcher Windows `START_REPORT.bat`, Streamlit localhost `http://127.0.0.1:8501`.

## Chạy local trên Windows

Yêu cầu Python 3.11+.

1. Mở thư mục dự án trên Windows.
2. Double-click `START_REPORT.bat`.
3. Khi terminal báo app đã chạy, mở `http://127.0.0.1:8501` nếu trình duyệt chưa tự mở.

Launcher tự tạo `.venv` nếu thiếu, cài `requirements.txt` nếu thiếu thư viện, rồi chạy Streamlit tại `127.0.0.1:8501`. Database SQLite nằm tại `data/tiktok_affiliate_report.db`.

## Chạy bằng EXE (máy không cần Python)

File đã đóng gói nằm tại `dist\TikTokAffiliateReport.exe`. Chỉ cần copy và double-click file này; app mở tại `http://127.0.0.1:8501` và tạo thư mục `data` cạnh EXE để lưu lâu dài.

EXE phát hành được build **không kèm database người dùng**. Máy mới khởi tạo database rỗng và chỉ tạo cấu hình KPI mặc định; dữ liệu phát sinh luôn nằm trong thư mục `data` cạnh EXE và không bị installer ghi đè. `BUILD_EXE.bat` tự chạy privacy gate và dừng nếu archive chứa file database.

Để build lại trên máy phát triển, double-click `BUILD_EXE.bat`. Không đặt EXE trong `Program Files`; dùng một thư mục người dùng có quyền ghi, ví dụ `Documents\TikTok Affiliate Report`.

## Tải bản cài đặt

GitHub Release private: https://github.com/anhtahaylove/tiktok-affiliate-report/releases/latest

- Đăng nhập GitHub bằng account có quyền đọc private repository rồi tải `TikTokAffiliateReportSetup-v1.0.0.exe`.
- `SHA256SUMS.txt` trong release dùng để kiểm tra file sau khi tải.
- Bản cài đặt được phân phối không cần code-signing trả phí. Windows SmartScreen có thể cảnh báo; hãy đối chiếu `SHA256SUMS.txt` trước khi chạy.

## Build installer Windows

Installer chuẩn Windows tạo bằng Inno Setup, cài app vào `%LOCALAPPDATA%\TikTokAffiliateReport`, thêm Start Menu, uninstaller và shortcut ngoài Desktop.

Cài công cụ build một lần trên máy phát triển:

```powershell
winget install --id JRSoftware.InnoSetup --exact
```

```powershell
.\packaging\build_installer.ps1
```

Output: `artifacts\installer\TikTokAffiliateReportSetup.exe`. Máy người dùng không cần cài Inno Setup hoặc Python.

Build hiện cố ý không đọc Windows Certificate Store và không code-sign artifact. Integrity được kiểm tra bằng SHA-256; có thể bổ sung signing sau nếu phạm vi phát hành thay đổi.

## Phase 2 API + Next.js/PWA

Streamlit/EXE vẫn là bản local ổn định. Phase 2 tái sử dụng cùng parser, dedupe và report core qua FastAPI.

Chạy local mặc định (anonymous local owner, chỉ được bind loopback):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe run_api.py
```

Sau đó chạy PWA:

```powershell
Set-Location web
Copy-Item .env.example .env.local
pnpm install
pnpm dev
```

Mở `http://127.0.0.1:3000`. API local tại `http://127.0.0.1:8000`.

Gate B hỗ trợ OIDC Authorization Code + PKCE, session/CSRF server-side, roles `owner`/`operator`/`viewer`, account allowlist và PostgreSQL. Ví dụ cấu hình PowerShell trước khi chạy API shared:

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

`AUTH_DEFAULT_ACCOUNTS` mặc định rỗng: user mới đăng nhập được nhưng chưa thấy dữ liệu cho đến khi owner cấp account qua `PATCH /api/v1/admin/users/{id}`. Không commit client secret hoặc PostgreSQL password.

Chuyển database local hiện có sang một PostgreSQL rỗng:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py `
  --source data\tiktok_affiliate_report.db `
  --target 'postgresql+psycopg://app:<PASSWORD>@127.0.0.1:5432/tiktok_affiliate_report'
```

Tool copy dữ liệu nghiệp vụ và user/account mapping, không copy session hoặc OIDC login state, rồi kiểm tra row counts và PostgreSQL sequences.

## Kiểm tra

```powershell
.\START_REPORT.bat --check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall streamlit_app.py tiktok_affiliate_report
.\.venv\Scripts\python.exe -m pip check
```

## Tài liệu

- [PRD](docs/PRD-TikTok-Affiliate-Report.md)
- [Input/output mapping](docs/DATA_MAPPING.md)
- [Database schema](docs/schema.sql)
- [Phase 2 architecture](docs/PHASE-2-ARCHITECTURE.md)

## Quy tắc dữ liệu

- File TikTok không chứa tên affiliate account sở hữu file; `Tên cửa hàng` là seller shop. Selector không có mặc định và người upload phải chọn đúng account; app không suy account từ filename.
- Không dedupe chỉ bằng `ID đơn hàng`: một order có thể có nhiều SKU.
- `Tổng số tiền nhận được cuối cùng` là KPI TikTok riêng, không phải `Hoa hồng thực tế` theo workbook.
- Một dòng không xuất hiện trong file sau không bị xem là đã xoá.
- `REPORT AFF.xlsx` là nguồn thiết kế output legacy đã chốt; app không cần link Google Sheets để chạy.
