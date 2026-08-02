# TikTok Affiliate Report PWA

Next.js/PWA client cho API Phase 2. Đây là nền web dùng chung cho browser, Tauri desktop và Capacitor mobile; Streamlit vẫn là app desktop ổn định trong Phase 1.

## Chạy local

Từ thư mục gốc, chạy API:

```powershell
python -m pip install -r requirements-api.txt
python run_api.py
```

Từ `web/`:

```powershell
Copy-Item .env.example .env.local
pnpm install
pnpm dev
```

Mở `http://127.0.0.1:3000`.

## PWA

- Manifest: `src/app/manifest.ts`
- Service worker: `public/sw.js`
- App shell có thể mở offline; dữ liệu báo cáo vẫn cần kết nối API.
- Production phải đặt API sau HTTPS/OIDC; API local hiện không phải public security boundary.
