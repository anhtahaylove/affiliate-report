import os

from affiliate_report.auth import is_loopback_host
from affiliate_report.api import app

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "127.0.0.1").strip()
    auth_mode = os.getenv("AUTH_MODE", "local").strip().lower()
    if auth_mode != "oidc" and not is_loopback_host(host):
        raise RuntimeError("AUTH_MODE=local chỉ được bind loopback; dùng AUTH_MODE=oidc trước khi expose API.")
    uvicorn.run(app, host=host, port=int(os.getenv("API_PORT", "8000")))
