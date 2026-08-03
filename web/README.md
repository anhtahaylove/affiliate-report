# TikTok Affiliate Report PWA

Next.js/PWA Operations Cockpit cho FastAPI. Đây là UI production dùng chung cho browser, bộ cài Windows hiện tại và các wrapper Tauri/Capacitor khi có nhu cầu native thật.

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
- Production đặt API sau HTTPS với `AUTH_MODE=oidc`; PWA dùng cookie session/CSRF, không lưu token trong `localStorage`.
