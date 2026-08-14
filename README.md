# Affiliate Report

Web app local cho Windows để import Excel export từ TikTok Affiliate, chống double-count khi file bị overlap và theo dõi hiệu suất theo từng affiliate account. UI production là **Next.js Momentum Canvas**; Python/FastAPI giữ toàn bộ parser, dedupe, versioning và công thức báo cáo.

## Chức năng

- Parser đúng 47 cột TikTok; giữ ID dạng text và raw JSON để audit.
- Giới hạn upload 20 MB và 50.000 dòng/file.
- Dedupe file bằng SHA-256; versioning theo `account + order_id + sku_id` khi dữ liệu thay đổi.
- Dashboard `ALL` và từng account: đơn hàng, GMV, hoa hồng, huỷ, KPI ngày/tháng.
- Sửa KPI/ngày theo từng account; owner sửa thêm target tổng `ALL`.
- Upload `.xlsx`, phản hồi duplicate/inserted/updated/unchanged/rejected và lịch sử import gần nhất.
- Hybrid Pairing gửi file từ điện thoại: ưu tiên cùng Wi-Fi/LAN hoặc dùng Cloudflare relay khi hai thiết bị khác mạng; nội dung được mã hóa AES-256-GCM trước khi lên cloud.
- Roles `owner` / `operator` / `viewer`, account allowlist, OIDC session + CSRF cho shared web.
- SQLite cho local single-user; PostgreSQL cho shared multi-user.
- PWA responsive dùng chung cho web/desktop, sẵn boundary để bọc mobile sau này.

## Cài và chạy trên máy Windows không cần Python

Tải installer từ [public GitHub Releases](https://github.com/anhtahaylove/affiliate-report/releases), đối chiếu `SHA256SUMS.txt`, rồi chạy `AffiliateReportSetup-v2.0.30.exe`.

Installer cài theo user vào `%LOCALAPPDATA%\AffiliateReport`, tạo shortcut Desktop/Start Menu. Double-click app sẽ:

1. khởi động FastAPI trên một cổng loopback còn trống;
2. phục vụ Next.js đã bundle cùng EXE;
3. tạo biểu tượng ở Windows system tray;
4. tự mở `http://127.0.0.1:<port>` trong trình duyệt.

App chỉ chạy một instance. Nếu mở shortcut lần nữa, instance mới sẽ mở lại dashboard hiện tại rồi tự thoát.

### Cách cài và mở app

1. Tải file setup mới nhất và `SHA256SUMS.txt` từ public Releases.
2. Mở PowerShell tại thư mục tải xuống và kiểm tra hash nếu cần:

   ```powershell
   Get-FileHash .\AffiliateReportSetup-v2.0.30.exe -Algorithm SHA256
   ```

   Giá trị phải trùng dòng tương ứng trong `SHA256SUMS.txt`.
3. Double-click setup. Vì app chưa có Authenticode, nếu SmartScreen hiện cảnh báo thì chọn **More info** → **Run anyway** sau khi đã kiểm tra hash.
4. Giữ tuỳ chọn tạo shortcut Desktop, hoàn tất cài đặt rồi mở **Affiliate Report** từ Desktop hoặc Start Menu.
5. Chờ vài giây; app tự mở trình duyệt tại một địa chỉ `http://127.0.0.1:<port>` chỉ truy cập được trên chính máy đó.

Lần đầu sử dụng: vào **Accounts** tạo account, vào **Imports** chọn account và upload file TikTok `.xlsx`, sau đó xem **Dashboard**/**Analytics** và đặt KPI tại **Targets**. Scope **ALL** tự tổng hợp các account; không upload file vào **ALL**.

Trong **Imports → Gửi tệp từ điện thoại**, chọn **Cùng Wi-Fi** để gửi trực tiếp tới máy tính hoặc **Khác mạng** để dùng Cloud Pairing tại `aff-report.huuhungn.io.vn`. Máy người dùng không cần tài khoản Cloudflare hay cấu hình domain; relay dùng chung chỉ giữ ciphertext tối đa 15 phút và xóa ngay sau khi desktop xác nhận đã nhận. URL `workers.dev` của cùng Worker được nhúng làm fallback khi custom domain tạm lỗi.

### Mở lại, đóng app và xử lý lỗi

- Mở lại: dùng shortcut Desktop hoặc Start Menu; không cần chạy command.
- App không có cửa sổ desktop riêng; trình duyệt chính là giao diện. Đóng tab trình duyệt không dừng backend.
- Muốn dừng hoàn toàn: dùng nút **Thoát ứng dụng** trên web app, hoặc nhấp phải biểu tượng tray và chọn **Thoát ứng dụng**.
- Muốn mở lại dashboard khi app đang chạy: double-click biểu tượng tray hoặc mở shortcut lần nữa.
- Nếu trình duyệt không tự mở: mở shortcut lần nữa hoặc chọn **Mở Affiliate Report** trong tray. Log chẩn đoán nằm tại `%LOCALAPPDATA%\AffiliateReport\data\launcher.log`.
- Nếu app bị chặn khi cài/chạy: kiểm tra SmartScreen/antivirus và xác minh SHA-256 trước khi cho phép.
- Update hoặc cài lại giữ nguyên database. Muốn xoá lịch sử, dùng **Settings → Data → Reset Data** để app backup trước; không dùng reinstall để reset.

Máy người dùng không cần Python, Node.js, pnpm, Docker hoặc Railway. Dữ liệu nằm tại `%LOCALAPPDATA%\AffiliateReport\data\affiliate_report.db` và không được nhúng vào installer hay ghi đè khi nâng cấp/cài lại. Đây là chủ ý để giữ lịch sử; muốn làm mới dữ liệu phải thực hiện thao tác reset riêng, không dùng reinstall.

Mỗi máy cài đặt hoạt động độc lập với database riêng. Người dùng chỉ cần cài full installer rồi chạy local; domain, Cloudflare Tunnel, OIDC và PostgreSQL chỉ cần khi chủ động chuyển sang mô hình dùng chung nhiều người.

Owner có thể dùng mục **Reset Data** trong dashboard local. App bắt buộc nhập cụm xác nhận, tạo backup đầy đủ tại `%LOCALAPPDATA%\AffiliateReport\data\backups`, kiểm tra backup rồi mới xoá lịch sử import và đơn hàng. Account, target, cấu hình đăng nhập và tùy chọn giao diện được giữ nguyên.

Mục **Khôi phục backup** liệt kê thời gian, dung lượng và row counts để xem trước. Restore chỉ thay các bảng dữ liệu báo cáo, giữ nguyên user/session đang dùng và luôn tạo thêm một safety backup của trạng thái hiện tại trước khi ghi đè.

Mục **Cập nhật phiên bản** tự check một lần khi owner mở dashboard và có nút kiểm tra lại. App đọc public feed `stable.json` + `stable.json.sig` từ `anhtahaylove/affiliate-report`, xác minh chữ ký Ed25519 bằng public key ghim trong app, rồi mới tải installer HTTPS đúng tên/kích thước/SHA-256. Không cần GitHub token trên máy người dùng; biến `TIKTOK_REPORT_UPDATE_FEED_URL` chỉ dùng được khi chạy source/dev, không dùng trong bản cài frozen.

Kết quả helper/installer được ghi tại `%LOCALAPPDATA%\AffiliateReport\data\updater.log` và thư mục `data\updates\v<version>` để chẩn đoán nếu update bị Windows hoặc antivirus chặn.

Artifact hiện cố ý **không code-sign**; Windows SmartScreen có thể cảnh báo và làm gián đoạn bước cài tự động cho tới khi người dùng chấp thuận. SHA-256 xác minh integrity, không thay thế publisher trust.

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

## Shared web tùy chọn với OIDC + PostgreSQL

Shared multi-user cần PostgreSQL, OIDC provider thật, TLS/reverse proxy và secret injection ngoài Git:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://app:<PASSWORD>@127.0.0.1:5432/affiliate_report'
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

`AUTH_ALLOWED_EMAILS` là chính sách truy cập liên tục, không chỉ là danh sách cho lần đăng nhập đầu. Mỗi OIDC login và mỗi request của session đang hoạt động đều kiểm tra email hiện tại: email phải khớp `AUTH_BOOTSTRAP_OWNER_EMAIL` hoặc nằm trong `AUTH_ALLOWED_EMAILS`. Sau khi đổi biến môi trường và khởi động lại service, session không còn hợp lệ bị thu hồi ở request tiếp theo. Cờ `active` trong trang **Người dùng** vẫn được áp dụng, nhưng không thể vượt qua allowlist.

Trong PostgreSQL dùng chung, **Cài đặt → Dữ liệu** chỉ hiển thị trạng thái quản trị hạ tầng; app không chạy Reset Data, backup hoặc restore kiểu file SQLite. **Cài đặt → Cập nhật** cũng không chạy installer Windows: phiên bản phải được triển khai tại máy chủ. API `/api/v1/meta` công bố capability và lý do để frontend không gọi nhầm endpoint local-only.

Chuyển database SQLite local sang PostgreSQL rỗng:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py `
  --source data\affiliate_report.db `
  --target 'postgresql+psycopg://app:<PASSWORD>@127.0.0.1:5432/affiliate_report'
```

Tool copy dữ liệu nghiệp vụ và user/account mapping, không copy session/OIDC state, rồi kiểm tra row counts và PostgreSQL sequences.

## Build full installer

```powershell
.\BUILD_EXE.bat
.\packaging\build_installer.ps1 -SkipAppBuild
```

Artifact phát hành:

- `artifacts\installer\AffiliateReportSetup-v2.0.30.exe`
- `artifacts\installer\TikTokAffiliateUpdater-v1.0.0.ps1`
- `artifacts\installer\SHA256SUMS.txt`
- `artifacts\installer\stable.json`
- `artifacts\installer\stable.json.sig`

Không phát hành portable EXE. `BUILD_EXE.bat` chỉ tạo runtime staging nội bộ để Inno Setup đóng gói, đồng thời chạy privacy gate để chặn database người dùng lọt vào installer. Build installer cần Inno Setup 6 trên máy phát triển:

```powershell
winget install --id JRSoftware.InnoSetup --exact
```

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q affiliate_report scripts tests desktop_launcher.py
.\.venv\Scripts\python.exe -m pip check
pnpm --dir web lint
pnpm --dir web test:unit
pnpm --dir web exec tsc --noEmit
pnpm --dir web build
git diff --check
```

Kịch bản end-to-end chạy thật qua trình duyệt (tạo tài khoản → nhập file mẫu → đọc số liệu → hoàn tác). Cần build `web/out` trước và tải Chromium một lần:

```powershell
pnpm --dir web build
pnpm --dir web exec playwright install chromium
pnpm --dir web test:e2e
```

Kịch bản này cố ý không nằm trong CI: mỗi lần chạy phải tải trình duyệt vài trăm MB, trong khi nó kiểm đúng luồng mà người dùng cũng sẽ tự chạy trên máy trước khi phát hành.

## Tài liệu

- [PRD](docs/PRD-TikTok-Affiliate-Report.md)
- [Input/output mapping](docs/DATA_MAPPING.md)
- [Database schema](docs/schema.sql)
- [Phase 2 architecture](docs/PHASE-2-ARCHITECTURE.md)
- [Hybrid Pairing trên Cloudflare](docs/HYBRID-PAIRING-CLOUDFLARE.md)

## Quy tắc dữ liệu

- File TikTok không chứa tên affiliate account sở hữu file; `Tên cửa hàng` là seller shop. Người upload phải chọn account, app không suy account từ filename.
- Không dedupe chỉ bằng `ID đơn hàng`: một order có thể có nhiều SKU.
- `Tổng số tiền nhận được cuối cùng` là KPI TikTok riêng, không phải `Hoa hồng thực tế` theo workbook.
- Một dòng không xuất hiện trong file sau không bị xem là đã xoá.
- Một dòng hỏng chỉ làm mất đúng dòng đó; phần còn lại của file vẫn được nhập và dòng bị loại được báo kèm số dòng.
- Nhập nhầm file thì dùng **Hoàn tác lần nhập này** trong Nhập dữ liệu, không cần reset toàn bộ.
- `REPORT AFF.xlsx` là nguồn thiết kế output legacy; app không cần link Google Sheets để chạy.

## Đổi tên từ v2.0.29

Ứng dụng trước đây tên là *TikTok Affiliate Report*, nay là **Affiliate Report** — tên cũ mang
nhãn hiệu không thuộc về dự án. Cách dùng không đổi: vẫn đọc đúng tệp Excel do TikTok Shop xuất
ra, vẫn 47 cột như cũ.

Đường dẫn đổi theo: thư mục cài `%LOCALAPPDATA%\AffiliateReport` cho máy cài mới, tệp dữ liệu
`affiliate_report.db`, và tệp cài đặt mang tiền tố `AffiliateReportSetup`.

Máy đã cài từ trước **giữ nguyên thư mục cũ** — Windows nhớ nơi đã cài và cài đè đúng chỗ đó,
nên không có gì phải di chuyển. Tệp database được đổi tên tự động lúc mở app, bản cũ vẫn nằm
nguyên bên cạnh làm dự phòng. Không tệp nào bị xoá.
