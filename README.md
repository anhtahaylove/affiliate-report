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
- Bản `v1.0.0` hiện dùng chữ ký self-signed local nên Windows SmartScreen có thể cảnh báo. Chỉ coi là public-trusted sau khi pipeline build chạy với OV/EV hoặc Azure Artifact Signing và timestamp hợp lệ.

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

Script sẽ ký `dist\TikTokAffiliateReport.exe` và installer nếu trong `Cert:\CurrentUser\My` có code-signing certificate còn hạn kèm private key. Nếu máy chưa có certificate, dùng signing local/dev:

```powershell
.\packaging\build_installer.ps1 -CreateSelfSignedCert
```

Self-signed signature chỉ giúp kiểm tra integrity nội bộ; Windows/SmartScreen vẫn có thể cảnh báo vì không phải certificate public-trusted.

Khi có certificate code-signing public-trusted, chọn đúng certificate và timestamp bản phát hành:

```powershell
.\packaging\build_installer.ps1 `
  -CertificateThumbprint "<THUMBPRINT>" `
  -TimestampServer "http://timestamp.digicert.com" `
  -RequireTrustedCertificate
```

Public release gate yêu cầu exact thumbprint, certificate không self-signed, signature hợp lệ trên máy build và RFC 3161/SHA-256 timestamp. Script không tự dùng certificate của ứng dụng khác trên máy.

## Phase 2 API + Next.js/PWA

Streamlit/EXE vẫn là bản local ổn định. Foundation Phase 2 tái sử dụng cùng parser, dedupe và report core qua FastAPI:

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

Mở `http://127.0.0.1:3000`. API local tại `http://127.0.0.1:8000`; chưa được expose public trước khi có OIDC.

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
