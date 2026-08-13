from __future__ import annotations

import ctypes
import json
import os
import secrets
import shutil
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import urlopen

from affiliate_report.version import APP_VERSION


HOST = "127.0.0.1"
MUTEX_NAME = r"Local\AffiliateReport.SingleInstance"
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
    temp_path.write_text(
        json.dumps({"pid": os.getpid() if running else None, "url": url, "app_version": APP_VERSION}),
        encoding="utf-8",
    )
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
        "AffiliateReport",
        image,
        "Affiliate Report",
        menu=pystray.Menu(
            pystray.MenuItem(
                "Mở Affiliate Report",
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


# Quét thư mục nhập mỗi chừng này. Không dùng thư viện theo dõi hệ thống tệp: dịch vụ đồng bộ
# ghi tệp theo nhiều đợt nên sự kiện "tệp mới" bắn nhiều lần cho một tệp, và quét định kỳ vài
# giây thì đơn giản hơn hẳn mà người dùng không thấy khác biệt.
INBOX_SCAN_SECONDS = 15


def _start_inbox_watcher(app: object, data_dir: Path) -> None:
    """Tự nhập tệp TikTok thả vào <data>/inbox/<ACCOUNT>/.

    Có để người dùng xuất tệp trên điện thoại rồi lưu vào một thư mục được đồng bộ (Drive,
    OneDrive, Syncthing) là máy tính tự nhập, khỏi phải chuyển tệp sang rồi mở trình duyệt.
    """
    from affiliate_report.accounts import active_account_codes
    from affiliate_report.inbox import ensure_inbox, scan_inbox

    def loop() -> None:
        engine = app.state.engine  # type: ignore[attr-defined]
        try:
            root = ensure_inbox(data_dir, list(active_account_codes(engine)))
            print(f"Inbox watcher: tha tep TikTok vao {root} / <MA ACCOUNT>")
        except Exception as exc:  # noqa: BLE001
            print(f"Inbox watcher khong khoi dong duoc: {exc}")
            return
        while True:
            time.sleep(INBOX_SCAN_SECONDS)
            try:
                for result in scan_inbox(engine, data_dir):
                    if result.status != "skipped":
                        print(f"Inbox {result.account}/{result.filename}: {result.status} - {result.detail}")
            except Exception as exc:  # noqa: BLE001 - vong nay khong duoc chet, chi ghi log roi di tiep
                print(f"Inbox watcher loi: {exc}")

    threading.Thread(target=loop, name="inbox-watcher", daemon=True).start()


# Hai hằng số LEGACY_* phải giữ NGUYÊN VĂN tên cũ — chúng là thứ duy nhất còn biết dữ liệu của
# người dùng đang nằm ở đâu trước khi đổi tên. Đổi chúng theo là di trú thành vô nghĩa và người
# dùng mở app lên thấy trống rỗng. Một lần thay chuỗi hàng loạt đã suýt làm đúng điều đó.
LEGACY_DATA_DIR_NAME = "TikTokAffiliateReport"
LEGACY_DATABASE_NAME = "tiktok_affiliate_report.db"
DATABASE_NAME = "affiliate_report.db"


def _di_tru_du_lieu(data_dir: Path) -> None:
    """Đưa dữ liệu cũ sang chỗ mới trước khi bất cứ ai mở database.

    Đợt đổi tên thương hiệu làm đổi cả thư mục cài lẫn tên tệp database. Không có bước này thì
    người dùng cập nhật xong mở app lên thấy TRỐNG RỖNG — ứng dụng lặng lẽ tạo database mới bên
    cạnh database cũ, không báo lỗi gì, và mọi lịch sử nhập coi như biến mất.

    Cả hai bước đều CHÉP chứ không xoá bản cũ: nếu có gì sai thì dữ liệu gốc vẫn nằm nguyên đó.
    """
    # 1. Thư mục cài đổi tên: bản cài mới trỏ vào thư mục trống, dữ liệu nằm ở thư mục cũ.
    thu_muc_cu = data_dir.parent.parent / LEGACY_DATA_DIR_NAME / "data"
    if thu_muc_cu.is_dir() and thu_muc_cu != data_dir and not any(data_dir.iterdir()):
        print(f"Di tru du lieu tu {thu_muc_cu} sang {data_dir}")
        shutil.copytree(thu_muc_cu, data_dir, dirs_exist_ok=True)

    # 2. Tệp database đổi tên trong cùng một thư mục.
    cu, moi = data_dir / LEGACY_DATABASE_NAME, data_dir / DATABASE_NAME
    if cu.is_file() and not moi.exists():
        print(f"Doi ten database {cu.name} -> {moi.name}")
        shutil.copy2(cu, moi)


def main() -> None:
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    run_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else bundle_dir
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        _di_tru_du_lieu(data_dir)
    except OSError as exc:
        # Không được chặn khởi động vì việc này: app vẫn mở được với dữ liệu sẵn có.
        print(f"Di tru du lieu that bai, bo qua: {exc}")
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
    os.environ["DATABASE_URL"] = f"sqlite:///{(data_dir / DATABASE_NAME).as_posix()}"
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

        from affiliate_report.api import app

        _start_inbox_watcher(app, data_dir)

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
