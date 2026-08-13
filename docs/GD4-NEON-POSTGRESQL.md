# Chuyển sang Neon PostgreSQL và đăng nhập Google

Tài liệu này ghi phần đã kiểm chứng được bằng máy, và phần buộc phải làm bằng tay trên tài
khoản của bạn. Đọc mục "Ràng buộc Google chặn" trước khi lên kế hoạch nhiều người dùng — nó
quyết định kiến trúc, không phải chi tiết cấu hình.

## 1. Diễn tập chuyển dữ liệu — đã chạy thật, khớp tuyệt đối

Chạy `scripts/migrate_sqlite_to_postgres.py` trên **bản copy** database thật (5.508 dòng) sang
PostgreSQL 16, rồi đối chiếu từng con số:

| | SQLite | PostgreSQL |
|---|---|---|
| Số dòng đơn | 5.508 | 5.508 |
| Tổng GMV | 552.580.408 | 552.580.408 |
| Tổng hoa hồng | 49.216.461 | 49.216.461 |
| Tiền nhận cuối | 38.522.563 | 38.522.563 |
| Số dòng gốc | 5.508 | 5.508 |
| Số lần nhập | 3 | 3 |
| Mục tiêu tháng | 6 | 6 |

Báo cáo tổng quan dựng từ hai bên **giống hệt nhau**. Toàn bộ bộ test cũng đã chạy trên
PostgreSQL thật, không còn test nào bị bỏ qua.

Chuỗi kết nối Neon dùng được nguyên trạng: `db.py` tự đổi tiền tố `postgres://` và
`postgresql://` sang `postgresql+psycopg://`, nên dán thẳng chuỗi Neon đưa cho là chạy.

Nên chuyển **sau** khi đã gỡ lưu trùng `raw_json` (đã làm): database từ 45,7 MB xuống 26,28 MB,
nghĩa là chuyển đi một nửa số byte và ngốn ít hạn mức 0,5 GB của gói miễn phí hơn hẳn.

## 2. Ràng buộc Google chặn — kiểm chứng từ tài liệu chính thức

Trích [tài liệu OAuth 2.0 của Google](https://developers.google.com/identity/protocols/oauth2/web-server):

> "Redirect URIs must use the HTTPS scheme, not plain HTTP. Localhost URIs (including localhost
> IP address URIs) are exempt from this rule."
>
> "Hosts cannot be raw IP addresses. Localhost IP addresses are exempted from this rule."

Ba hệ quả thẳng vào kế hoạch:

| Cách dùng | Đăng nhập Google có được không |
|---|---|
| App máy bàn, `http://127.0.0.1:<cổng>/…` | **Được** — loopback được miễn trừ |
| Nhiều người vào qua LAN, `http://192.168.1.50:8000/…` | **Không** — vừa là HTTP thuần, vừa là IP thô |
| App điện thoại gọi về máy bạn qua IP | **Không** — cùng lý do |
| Có tên miền riêng chạy HTTPS | **Được** |

Nói gọn: **đăng nhập Google không phải thứ bật lên là dùng được cho nhiều người trong mạng
LAN.** Muốn 3–5 người cùng dùng bằng tài khoản Google thì phải có một tên miền công khai chạy
HTTPS trỏ về nơi đặt ứng dụng — không có đường vòng nào qua IP nội bộ.

Việc này **không** ảnh hưởng tới bản máy bàn đang chạy: nó dùng loopback nên vẫn đăng nhập
Google được bình thường, và chế độ `local` hiện tại không đụng gì tới Google.

## 3. Việc bạn phải tự làm — tôi không có quyền vào tài khoản của bạn

### 3.1. Dựng dự án Neon và **bật hạn mức chi tiêu ngay**

1. Vào <https://console.neon.tech>, tạo project, chọn region gần Việt Nam nhất
   (Singapore `ap-southeast-1`).
2. **Trước khi nhập dữ liệu**: vào *Settings → Billing* đặt hạn mức chi tiêu. Gói miễn phí cho
   0,5 GB; đặt hạn mức để vượt ngưỡng thì nó chặn chứ không âm thầm tính tiền.
3. Copy chuỗi kết nối (dạng
   `postgresql://user:pass@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`).

### 3.2. Chuyển dữ liệu

```powershell
# Sao lưu trước, luôn luôn.
Copy-Item data\affiliate_report.db data\truoc-khi-chuyen-neon.db

.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py `
  --source data\affiliate_report.db `
  --target "<chuoi-ket-noi-neon>"
```

Script tự từ chối nếu database đích đã có dữ liệu, và không in mật khẩu ra khi báo lỗi.

### 3.3. Nếu vẫn muốn đăng nhập Google

Cần một tên miền HTTPS công khai. Sau khi có:

1. Google Cloud Console → *APIs & Services → Credentials → Create OAuth client ID → Web
   application*.
2. Authorized redirect URI: `https://<tên-miền-của-bạn>/api/v1/auth/oidc/callback`.
3. Đặt biến môi trường:

```
AUTH_MODE=oidc
OIDC_ISSUER=https://accounts.google.com
OIDC_CLIENT_ID=<...>
OIDC_CLIENT_SECRET=<...>
OIDC_REDIRECT_URI=https://<tên-miền-của-bạn>/api/v1/auth/oidc/callback
DATABASE_URL=<chuoi-ket-noi-neon>
```

Chưa có tên miền thì dừng ở mục 3.1–3.2: dùng Neon làm nơi chứa dữ liệu chung, còn đăng nhập
giữ nguyên chế độ hiện tại.

## 4. Bản máy bàn vẫn chạy song song

Đặt `DATABASE_URL` trỏ Neon chỉ đổi nơi chứa dữ liệu, không đụng gì tới cách khởi động. Không
đặt biến đó thì ứng dụng vẫn dùng SQLite trong `%LOCALAPPDATA%` như cũ, nên bản đã cài trên máy
không bị ảnh hưởng và chạy song song được.

Một điểm cần biết: Neon **ngủ khi không dùng**. Lần gọi đầu sau khi ngủ mất vài giây để dựng
lại kết nối. Đó là cái giá của việc không tính tiền lúc rảnh, và cũng là lý do chọn Neon thay
vì Supabase với sàn 25 USD/tháng.
