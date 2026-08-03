# Changelog

## Unreleased

- Operations Cockpit Next.js thay hoàn toàn Streamlit trong local runtime và Windows packaging.
- Editable KPI/ngày theo từng account; owner có thêm target tổng `ALL`.
- Dashboard responsive gồm filter, KPI tháng, daily/account performance, upload và import history.
- Windows EXE phục vụ static Next.js qua FastAPI trên cổng loopback tự chọn; máy người dùng không cần Python/Node/Docker.
- Gate B: OIDC Authorization Code + PKCE, server-side session/CSRF và role/account authorization.
- PostgreSQL shared database support, SQLite → PostgreSQL migration tool và Postgres 16 CI.
- PWA login/logout flow; viewer read-only, operator bị giới hạn account, `ALL` chỉ owner chỉnh sửa.
- Windows packaging mặc định unsigned; SHA-256 là integrity gate miễn phí.

## v1.0.0 - 2026-08-03

- Local Streamlit dashboard và Windows EXE/installer không cần Python.
- Import TikTok `.xlsx`, chống import trùng và version hóa order line overlap.
- Dashboard overview, daily, monthly KPI, orders và import history theo `REPORT AFF.xlsx`.
- Installer cài theo user, tạo Desktop shortcut và giữ nguyên database khi nâng cấp.
- Privacy gate chặn database người dùng bị nhúng vào EXE phát hành.
- Phase 2 foundation: FastAPI `/api/v1` và Next.js PWA responsive.

### Windows status

Artifact có thể unsigned/self-signed và Windows SmartScreen có thể cảnh báo. Private release kèm `SHA256SUMS.txt` để kiểm tra integrity.
