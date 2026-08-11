from __future__ import annotations

import ctypes
import json
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import urlopen


HOST = "127.0.0.1"
MUTEX_NAME = r"Local\TikTokAffiliateReport.SingleInstance"
ERROR_ALREADY_EXISTS = 183


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind((HOST, port))
            return True
        except OSError:
            return False


def _preferred_port(state_path: Path) -> tuple[int, bool]:
    """Dùng lại cổng của lần chạy trước nếu còn trống.

    Trước đây mỗi lần mở app lấy một cổng ngẫu nhiên, nên sau khi tự cập nhật thì tab trình duyệt
    đang mở trỏ vào một cổng đã chết và buộc phải mở tab mới — người dùng nhận hai tab, một cái
    hỏng. Giữ nguyên cổng thì chính tab đó tự kết nối lại, không cần mở thêm gì.
    """
    previous = _read_instance_url(state_path)
    if previous:
        port = urlsplit(previous).port
        if port and _port_is_free(port):
            return port, True
    return _free_port(), False


def _open_browser_when_ready(url: str) -> None:
    for _ in range(80):
        try:
            with urlopen(f"{url}/health", timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url, new=2)
                    return
        except OSError:
            time.sleep(0.25)


def _acquire_single_instance() -> tuple[int | None, bool]:
    if os.name != "nt":
        return None, True

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None, False
    return int(handle), True


def _release_single_instance(handle: int | None) -> None:
    if os.name != "nt" or handle is None:
        return
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)


def _read_instance_url(state_path: Path) -> str | None:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        value = payload.get("url")
        parsed = urlsplit(value) if isinstance(value, str) else None
        if (
            parsed is None
            or parsed.scheme != "http"
            or parsed.hostname != HOST
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or parsed.port is None
        ):
            return None
        return f"http://{HOST}:{parsed.port}"
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _open_existing_instance(state_path: Path) -> bool:
    for _ in range(40):
        url = _read_instance_url(state_path)
        if url:
            try:
                with urlopen(f"{url}/health", timeout=0.5) as response:
                    if response.status == 200:
                        webbrowser.open(url, new=2)
                        return True
            except OSError:
                pass
        time.sleep(0.25)
    return False


def _write_instance_state(state_path: Path, url: str, *, running: bool = True) -> None:
    temp_path = state_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps({"pid": os.getpid() if running else None, "url": url}), encoding="utf-8")
    os.replace(temp_path, state_path)


def _clear_instance_state(state_path: Path, url: str | None = None) -> None:
    """Giữ lại URL của lần chạy cuối nhưng bỏ pid. Mọi nơi đọc file này đều gọi /health trước khi
    tin, nên file còn lại không đánh lừa ai; đổi lại lần chạy sau biết cổng nào nên dùng lại."""
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        if payload.get("pid") != os.getpid():
            return
        last_url = url or payload.get("url")
        if isinstance(last_url, str) and last_url:
            _write_instance_state(state_path, last_url, running=False)
        else:
            state_path.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError):
        pass


def _start_tray(icon_path: Path, url: str, shutdown: Callable[[], None]):
    if os.name != "nt":
        return None, None

    os.environ.setdefault("PYSTRAY_BACKEND", "win32")
    import pystray
    from PIL import Image

    with Image.open(icon_path) as source:
        image = source.convert("RGBA")
    tray = pystray.Icon(
        "TikTokAffiliateReport",
        image,
        "TikTok Affiliate Report",
        menu=pystray.Menu(
            pystray.MenuItem(
                "Mở TikTok Affiliate Report",
                lambda _icon, _item: webbrowser.open(url, new=2),
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Thoát ứng dụng", lambda _icon, _item: shutdown()),
        ),
    )
    thread = threading.Thread(target=tray.run, name="system-tray", daemon=True)
    thread.start()
    return tray, thread


def main() -> None:
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    run_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else bundle_dir
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):
        log = (data_dir / "launcher.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log

    state_path = data_dir / "instance.json"
    relaunched_by_updater = "--updated" in sys.argv[1:]
    mutex_handle, is_primary = _acquire_single_instance()
    if not is_primary:
        if not _open_existing_instance(state_path):
            print("Existing instance detected but its local URL was unavailable.")
        return

    forced_port = os.getenv("API_PORT")
    if forced_port:
        port, reused_port = int(forced_port), False
    else:
        port, reused_port = _preferred_port(state_path)
    url = f"http://{HOST}:{port}"
    os.chdir(run_dir)
    os.environ["AUTH_MODE"] = "local"
    os.environ["DATABASE_URL"] = f"sqlite:///{(data_dir / 'tiktok_affiliate_report.db').as_posix()}"
    os.environ["DESKTOP_CONTROL_TOKEN"] = secrets.token_urlsafe(32)
    os.environ["WEB_APP_URL"] = url
    os.environ["WEB_STATIC_DIR"] = str(bundle_dir / "web")

    tray = tray_thread = None
    try:
        _write_instance_state(state_path, url)
        # Updater mở lại app bằng cờ --updated. Nếu giữ được đúng cổng cũ thì tab đang mở sẽ tự
        # kết nối lại và hiện bản mới, nên mở thêm tab nữa chỉ tạo tab trùng. Đổi cổng thì tab cũ
        # chắc chắn chết, lúc đó vẫn phải mở tab mới.
        if not (relaunched_by_updater and reused_port):
            threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
        else:
            print(f"Relaunched by updater on the same port {port}; leaving the existing tab to reconnect.")

        import uvicorn

        from tiktok_affiliate_report.api import app

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=HOST,
                port=port,
                loop="asyncio",
                http="h11",
                log_level="info",
            )
        )

        def shutdown() -> None:
            server.should_exit = True
            if tray is not None:
                tray.stop()

        app.state.update_shutdown = shutdown
        try:
            tray, tray_thread = _start_tray(bundle_dir / "packaging" / "app.ico", url, shutdown)
            if tray is not None:
                print("System tray started.")
        except Exception as exc:
            print(f"System tray unavailable: {exc}")
        server.run()
    finally:
        if tray is not None:
            tray.stop()
        if tray_thread is not None:
            tray_thread.join(timeout=3)
        _clear_instance_state(state_path, url)
        _release_single_instance(mutex_handle)
        if getattr(sys, "frozen", False):
            # Updater chờ tiến trình này thoát trong một khoảng có hạn rồi mới chạy installer,
            # nên thoát cứng để không phụ thuộc vào việc mọi thread nền có chịu dừng hay không.
            sys.stdout.flush()
            os._exit(0)


if __name__ == "__main__":
    main()
