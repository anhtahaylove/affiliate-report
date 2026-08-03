from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen


HOST = "127.0.0.1"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _open_browser_when_ready(url: str) -> None:
    for _ in range(80):
        try:
            with urlopen(f"{url}/health", timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url, new=2)
                    return
        except OSError:
            time.sleep(0.25)


def main() -> None:
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    run_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else bundle_dir
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):
        log = (data_dir / "launcher.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log

    port = int(os.getenv("API_PORT") or _free_port())
    url = f"http://{HOST}:{port}"
    os.chdir(run_dir)
    os.environ["AUTH_MODE"] = "local"
    os.environ["DATABASE_URL"] = f"sqlite:///{(data_dir / 'tiktok_affiliate_report.db').as_posix()}"
    os.environ["WEB_APP_URL"] = url
    os.environ["WEB_STATIC_DIR"] = str(bundle_dir / "web")

    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()

    import uvicorn

    from tiktok_affiliate_report.api import app

    server = uvicorn.Server(uvicorn.Config(
        app,
        host=HOST,
        port=port,
        loop="asyncio",
        http="h11",
        log_level="info",
    ))
    app.state.update_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()


if __name__ == "__main__":
    main()
