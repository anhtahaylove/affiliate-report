# Cloud Pairing Relay

Worker production cho Hybrid Pairing của Affiliate Report. Relay chỉ giữ ciphertext tạm thời;
AES key nằm trong URL fragment của QR và không được gửi tới Cloudflare.

## Local gates

```powershell
pnpm install
pnpm run check
```

## Provision/deploy

```powershell
pnpm wrangler whoami
pnpm wrangler r2 bucket create affiliate-report-pairing-temp
pnpm run deploy
```

`wrangler.jsonc` gắn Worker với custom domain `aff-report.huuhungn.io.vn` và vẫn bật
`workers.dev` làm endpoint dự phòng. Zone phải
đang Active trên Cloudflare và hostname không có CNAME/A record xung đột. Bucket R2 phải giữ
private; không bật `r2.dev`.

Không thêm Cloudflare token hoặc secret vào `.dev.vars`, source hoặc installer. Wrangler OAuth
chỉ dùng trên máy phát triển/CI để deploy.
