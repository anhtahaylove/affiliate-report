# Changelog

## v1.2.10 - 2026-08-05

- Trang Tài khoản chỉ còn một định danh — Mã tài khoản (đã bỏ "Tên hiển thị" riêng, dùng chung một giá trị duy nhất).
- Sửa lỗi hiển thị 0đ ở các đơn "Không đủ điều kiện": cột "Hoa hồng ước tính" trong bảng Đơn hàng và bảng "Theo trạng thái" trong Phân tích giờ hiện đúng số ước tính từ file gốc thay vì luôn là 0 (0đ vẫn đúng cho "Hoa hồng thực tế" tổng — đơn ineligible không tính vào tổng thực nhận, nhưng số ước tính của từng đơn không được phép biến mất khỏi màn hình).
- Thêm cột "Số món bán ra" vào bảng Đơn hàng và bảng So sánh hiệu suất (Dashboard), khớp với chỉ số REPORT_AFF.xlsx người dùng đang theo dõi thủ công.
- Bộ lọc Tài khoản/Trạng thái giờ giới hạn chiều cao ~3 hàng và cuộn nội bộ khi có nhiều lựa chọn, không còn đẩy cả trang xuống dài dằng dặc.

## v1.2.9 - 2026-08-05

- Không có thay đổi tính năng. Bản này chỉ để xác nhận thật bản vá "Installer exited with code 5" ở v1.2.8: cài v1.2.8 trực tiếp (không qua auto-update, do máy đang mắc kẹt ở bản lỗi cũ), rồi từ đó bấm cập nhật thật lên v1.2.9 qua đúng luồng trong app để chứng minh `Wait-FileUnlocked` hoạt động khi bên thực hiện cập nhật đã có bản vá.

## v1.2.8 - 2026-08-05

- Sửa lỗi cập nhật thất bại với "Installer exited with code 5" (Setup tự huỷ vì cho rằng ứng dụng còn đang chạy). Nguyên nhân: bước tự đóng app trước khi cài chỉ theo dõi đúng 1 tiến trình con, trong khi tiến trình cha của gói .exe onefile có thể còn giữ file .exe thêm vài trăm mili-giây để dọn dẹp thư mục tạm — installer chạy `/CLOSEAPPLICATIONS` đúng lúc đó, thấy file "đang bận" và Huỷ luôn vì chạy ở chế độ im lặng (không có hộp thoại để bấm Thử lại). Giờ updater chờ chắc chắn file .exe được nhả hoàn toàn (thử mở độc quyền, tối đa 15 giây) trước khi gọi installer, thay vì chỉ chờ đúng 1 tiến trình.

## v1.2.7 - 2026-08-05

- Chuẩn hoá màu tiến độ mục tiêu (Dashboard, So sánh hiệu suất, Mục tiêu) theo kiểu đèn giao thông: xanh khi đạt (≥100%), vàng khi còn 50–99%, đỏ khi dưới 50% — dùng lại đúng bộ màu trạng thái sẵn có của app, không thêm màu mới.
- Sửa hình dạng cột trong biểu đồ xu hướng Phân tích: bo góc trên, đáy phẳng neo vào trục — thay vì bo tròn đều 4 góc trông lơ lửng, đồng bộ với biểu đồ cột ở Dashboard.

## v1.2.6 - 2026-08-04

- Sửa lỗi tự đóng ứng dụng để cài bản cập nhật có thể treo ở popup Windows "Failed to remove temporary directory" (cảnh báo gốc từ PyInstaller khi không xoá được thư mục tạm `_MEI...` do vẫn còn thư viện đang được nạp). App giờ thoát tiến trình ngay sau khi đã dọn dẹp xong (tắt tray, lưu trạng thái, nhả khoá single-instance) thay vì để trình bao bọc PyInstaller tự dọn dẹp và có thể treo — updater không còn bị timeout chờ app đóng.

## v1.2.5 - 2026-08-04

- Trang Tài khoản chỉ còn CRUD tài khoản (thêm/sửa/lưu trữ/xóa); bảng so sánh hiệu suất đã dời hẳn về Dashboard, không còn trùng lặp và không còn bộ lọc gây hiểu nhầm phạm vi ảnh hưởng.
- Rút gọn tóm tắt Analytics từ 6 xuống 3 chỉ số không lặp với Dashboard (so kỳ trước, tỷ lệ hoa hồng hiệu dụng, độ mới dữ liệu), nhường trọng tâm cho xu hướng và xếp hạng.
- Thêm dòng chú thích phạm vi ảnh hưởng ngay dưới bộ lọc ở từng trang (Tổng quan, Phân tích, Đơn hàng, Mục tiêu).
- Gộp 3 mục Dữ liệu/Cập nhật/Người dùng thành một mục **Cài đặt** trên sidebar, chuyển sang dạng tab trong trang; URL từng trang không đổi.
- Dashboard dùng biểu đồ cột thật cho nhịp 14 ngày gần nhất thay vì chỉ bảng số; dọn code chết (`ProgressList`) không còn được dùng ở đâu.

## v1.2.4 - 2026-08-04

- Sửa lỗi auto-update trên Windows: helper không còn bị chặn bởi `DETACHED_PROCESS`, chuyển sang API .NET để chờ tiến trình, tính SHA-256 và chạy installer thay vì phụ thuộc `Get-FileHash`.
- App chỉ đóng sau khi helper xác nhận khởi động thành công (handshake); tải installer bằng background worker để không treo API.
- Giao diện Cập nhật hiển thị tiến độ thật theo phase `downloading → verifying → waiting_for_exit → installing → restarting → installed/failed`, kèm số MB và phần trăm.
- Khi cài đặt thất bại, tự khởi động lại phiên bản hiện tại và hiển thị nguyên nhân để thử lại.

## v1.2.3 - 2026-08-04

- Thu gọn bộ lọc trên mobile, hiển thị tóm tắt phạm vi và giữ đầy đủ thao tác khi mở rộng.
- Cải thiện Dashboard với thanh phạm vi báo cáo và nút xuất báo cáo ngày riêng, rõ ràng hơn.
- Liên kết cảnh báo dữ liệu tới đúng đơn hàng/import liên quan và hiển thị chi tiết tối đa 10 dòng nhập bị từ chối.
- Chuẩn hoá smoke installer theo tham số phiên bản để kiểm tra cài mới và nâng cấp cho mọi release tiếp theo.

## v1.2.2 - 2026-08-04

- Việt hoá trạng thái dashboard/analytics/order: Đã quyết toán, Không đủ điều kiện, Đang chờ quyết toán và Chưa xác định.
- Mặc định bộ lọc Account/Trạng thái chọn tất cả; giữ URL gọn khi đang ở scope ALL.
- Nút **Đặt lại bộ lọc** áp dụng canonical query ngay lập tức, không cần refresh.
- Xác minh smoke test nâng cấp Windows giữ nguyên dữ liệu cũ và đủ 9 route desktop/mobile.

## v1.2.1 - 2026-08-04

- Nâng GitHub Actions lên các major chạy Node.js 24 để loại cảnh báo Node.js 20 trong CI/release.
- Thêm smoke test installer trên Windows runner sạch cho cài mới v1.2.0 và nâng cấp v1.1.1 lên v1.2.0 có giữ dữ liệu.
- Khôi phục route **Settings → Data** từng bị rule `.gitignore` loại nhầm khỏi installer v1.2.0.
- Bổ sung hướng dẫn mở, chạy và xử lý lỗi app local cho người dùng cuối.
- Thêm system tray với hành động mở dashboard và thoát ứng dụng; web app cũng có nút **Thoát ứng dụng** chỉ hiện trong bản Windows local.
- Chặn chạy trùng bằng Windows named mutex; mở shortcut lần nữa sẽ mở lại dashboard của instance đang chạy.
- Nâng PostCSS lên 8.5.25 để vá cảnh báo bảo mật GHSA-fxqj-rqcc-2cmp.

## v1.2.0 - 2026-08-03

- Auto-update chuyển sang public signed feed `stable.json` + `stable.json.sig`, không cần token ở máy người dùng.
- App ghim Ed25519 `key_id`, chặn manifest sai chữ ký, downgrade, non-HTTPS, sai tên installer, sai kích thước hoặc sai SHA-256.
- Release workflow tạo private release bốn asset rồi mirror installer, checksum và signed stable feed sang `anhtahaylove/tiktok-affiliate-report-updates`.

## v1.1.1 - 2026-08-03

- Owner-only Reset Data yêu cầu xác nhận rõ ràng và tự động tạo/kiểm tra backup SQLite trước khi xoá lịch sử.
- Owner có thể xem trước backup, khôi phục riêng dữ liệu báo cáo và hệ thống tự tạo safety backup trước khi restore; user/session hiện tại được giữ nguyên.
- Dashboard tự kiểm tra GitHub Release mới nhất; bản Windows đã cài có thể tải, xác minh GitHub asset digest + `SHA256SUMS.txt`, đóng app, chạy installer qua helper và khởi động lại.
- Tag release tự build/test installer Windows, phát hành đúng hai asset và tải lại để kiểm tra SHA-256 trước khi publish.
- Local installer tiếp tục là chế độ mặc định; shared OIDC/PostgreSQL/domain/HTTPS hoàn toàn tùy chọn.

## v1.1.0 - 2026-08-03

- Operations Cockpit Next.js thay hoàn toàn Streamlit trong local runtime và Windows packaging.
- Editable KPI/ngày theo từng account; owner có thêm target tổng `ALL`.
- Dashboard responsive gồm filter, KPI tháng, daily/account performance, upload và import history.
- Windows EXE phục vụ static Next.js qua FastAPI trên cổng loopback tự chọn; máy người dùng không cần Python/Node/Docker.
- Gate B: OIDC Authorization Code + PKCE, server-side session/CSRF và role/account authorization.
- PostgreSQL shared database support, SQLite → PostgreSQL migration tool và Postgres 16 CI.
- PWA login/logout flow; viewer read-only, operator bị giới hạn account, `ALL` chỉ owner chỉnh sửa.
- Windows packaging mặc định unsigned; SHA-256 là integrity gate miễn phí.
- Chỉ phát hành full installer; portable EXE không còn là release artifact.
- Reinstall/upgrade giữ nguyên database và lịch sử người dùng theo installer contract.

## v1.0.0 - 2026-08-03

- Local Streamlit dashboard và Windows EXE/installer không cần Python.
- Import TikTok `.xlsx`, chống import trùng và version hóa order line overlap.
- Dashboard overview, daily, monthly KPI, orders và import history theo `REPORT AFF.xlsx`.
- Installer cài theo user, tạo Desktop shortcut và giữ nguyên database khi nâng cấp.
- Privacy gate chặn database người dùng bị nhúng vào EXE phát hành.
- Phase 2 foundation: FastAPI `/api/v1` và Next.js PWA responsive.

### Windows status

Artifact có thể unsigned/self-signed và Windows SmartScreen có thể cảnh báo. Private release kèm `SHA256SUMS.txt` để kiểm tra integrity.
