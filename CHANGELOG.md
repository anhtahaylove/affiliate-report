# Changelog

## v1.2.1 - 2026-08-03

- Nâng GitHub Actions lên các major chạy Node.js 24 để loại cảnh báo Node.js 20 trong CI/release.
- Thêm smoke test installer trên Windows runner sạch cho cài mới v1.2.0 và nâng cấp v1.1.1 lên v1.2.0 có giữ dữ liệu.
- Bổ sung hướng dẫn mở, chạy và xử lý lỗi app local cho người dùng cuối.

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
