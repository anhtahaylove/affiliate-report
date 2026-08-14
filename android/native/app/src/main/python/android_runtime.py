"""Start Affiliate Report's existing FastAPI application inside Chaquopy."""

from __future__ import annotations

import os
import threading
from pathlib import Path

_lock = threading.Lock()
_thread: threading.Thread | None = None
_server = None


def start(files_dir: str, cache_dir: str, web_dir: str, local_token: str, port: int = 8765) -> int:
    """Start exactly one loopback server for the lifetime of the Android process."""

    global _server, _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return port

        files = Path(files_dir).resolve()
        cache = Path(cache_dir).resolve()
        web = Path(web_dir).resolve()
        data_dir = files / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        if not isinstance(local_token, str) or len(local_token) < 32:
            raise ValueError("Android local token is missing or too short")

        os.environ.update(
            {
                "APP_PLATFORM": "android",
                "ANDROID_LOCAL_TOKEN": local_token,
                "AUTH_MODE": "local",
                "AUTH_COOKIE_SECURE": "false",
                "API_HOST": "127.0.0.1",
                "API_PORT": str(port),
                "DATABASE_URL": f"sqlite:///{(data_dir / 'affiliate_report.db').as_posix()}",
                "WEB_APP_URL": f"http://127.0.0.1:{port}",
                "WEB_STATIC_DIR": str(web),
                "TMPDIR": str(cache),
            }
        )
        os.chdir(files)

        import uvicorn
        from affiliate_report.api import app

        _server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                loop="asyncio",
                http="h11",
                log_level="warning",
                access_log=False,
            )
        )
        _thread = threading.Thread(target=_server.run, name="affiliate-report-api", daemon=True)
        _thread.start()
        return port


def is_running() -> bool:
    return bool(_thread and _thread.is_alive() and _server and _server.started)
