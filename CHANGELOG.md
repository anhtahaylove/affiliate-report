# Changelog

## v1.0.0 - 2026-08-03

- Local Streamlit dashboard và Windows EXE/installer không cần Python.
- Import TikTok `.xlsx`, chống import trùng và version hóa order line overlap.
- Dashboard overview, daily, monthly KPI, orders và import history theo `REPORT AFF.xlsx`.
- Installer cài theo user, tạo Desktop shortcut và giữ nguyên database khi nâng cấp.
- Privacy gate chặn database người dùng bị nhúng vào EXE phát hành.
- Phase 2 foundation: FastAPI `/api/v1` và Next.js PWA responsive.

### Signing status

Artifact hiện được ký bằng certificate self-signed local để kiểm tra packaging. OV/EV hoặc Azure Artifact Signing vẫn là release gate trước khi phân phối công khai ngoài nhóm có quyền truy cập private repository.
