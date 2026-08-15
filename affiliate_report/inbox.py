"""Nhập tệp TikTok thả vào một thư mục, thay cho việc phải mở trình duyệt và bấm tải lên.

Bối cảnh: người dùng xuất tệp trên điện thoại, và chuyển sang máy tính là bước cực nhất trong
cả quy trình. Cắm thư mục này vào một thư mục được đồng bộ (Drive, OneDrive, Syncthing) là
điện thoại lưu tệp xong thì máy tính tự nhập.

Cấu trúc thư mục — tên thư mục con quyết định account, vì tên tệp TikTok không nói nó thuộc
account nào:

    <data>/inbox/<MÃ ACCOUNT>/*.xlsx      tệp chờ nhập
    <data>/inbox/<MÃ ACCOUNT>/.done/      đã nhập xong
    <data>/inbox/<MÃ ACCOUNT>/.failed/    không nhập được, kèm .txt giải thích

Chỉ tệp tên bắt đầu bằng "affiliate_orders" mới được nhận (xem parser.is_valid_export_filename)
— thư mục đồng bộ chung (Drive, OneDrive, Download trên điện thoại) luôn lẫn cả tệp không liên
quan, tệp sai tên bị dời sang .failed kèm lý do chứ không lặng lẽ bỏ qua.

Trùng lặp không phải lo: import_rows đã băm SHA-256 nội dung tệp, thả lại đúng tệp cũ chỉ báo
"duplicate" chứ không nhân đôi dữ liệu.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from .accounts import active_account_codes
from .db import import_rows
from .parser import FILENAME_REJECT_MESSAGE, is_valid_export_filename, read_xlsx

INBOX_DIRNAME = "inbox"
DONE_DIRNAME = ".done"
FAILED_DIRNAME = ".failed"
MAX_INBOX_BYTES = 20 * 1024 * 1024

# Dịch vụ đồng bộ ghi tệp dần dần, nên tệp vừa xuất hiện có thể mới được một nửa. Đọc nửa tệp
# xlsx cho ra dữ liệu rác chứ không báo lỗi rõ ràng. Chỉ nhận tệp có kích thước và thời điểm
# sửa đổi không đổi qua hai lần nhìn cách nhau chừng này.
STABLE_CHECK_DELAY_SECONDS = 2.0


@dataclass(frozen=True)
class InboxResult:
    account: str
    filename: str
    status: str  # "imported" | "duplicate" | "rejected" | "skipped"
    detail: str
    counts: dict[str, int] | None = None


def inbox_dir(data_dir: Path) -> Path:
    return Path(data_dir).resolve() / INBOX_DIRNAME


def ensure_inbox(data_dir: Path, accounts: list[str]) -> Path:
    """Tạo sẵn thư mục cho từng account để người dùng biết thả tệp vào đâu."""
    root = inbox_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    for account in accounts:
        (root / account).mkdir(exist_ok=True)
    return root


def _is_stable(path: Path, delay: float = STABLE_CHECK_DELAY_SECONDS) -> bool:
    try:
        first = path.stat()
    except OSError:
        return False
    time.sleep(delay)
    try:
        second = path.stat()
    except OSError:
        return False
    if (first.st_size, first.st_mtime_ns) != (second.st_size, second.st_mtime_ns):
        return False
    # Đồng bộ xong nhưng tiến trình khác còn giữ tệp thì mở độc quyền sẽ hỏng.
    try:
        with path.open("rb"):
            return True
    except OSError:
        return False


def _move_aside(path: Path, folder: str, note: str | None = None) -> Path:
    target_dir = path.parent / folder
    target_dir.mkdir(exist_ok=True)
    target = target_dir / path.name
    if target.exists():
        target = target_dir / f"{path.stem}.{int(time.time())}{path.suffix}"
    shutil.move(str(path), str(target))
    if note:
        target.with_suffix(target.suffix + ".txt").write_text(note, encoding="utf-8")
    return target


def scan_inbox(engine: Engine, data_dir: Path, *, stable_delay: float = STABLE_CHECK_DELAY_SECONDS) -> list[InboxResult]:
    """Quét một lượt và nhập mọi tệp đã ổn định. Trả về kết quả từng tệp."""
    root = inbox_dir(data_dir)
    if not root.is_dir():
        return []

    known = {code.upper() for code in active_account_codes(engine)}
    results: list[InboxResult] = []

    for account_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        account = account_dir.name.strip().upper()
        files = sorted(p for p in account_dir.glob("*.xlsx") if p.is_file() and not p.name.startswith("~$"))
        if not files:
            continue
        if account not in known:
            for path in files:
                _move_aside(path, FAILED_DIRNAME, f"Không có account {account}. Hãy tạo account rồi thả lại tệp.")
                results.append(InboxResult(account, path.name, "rejected", f"Không có account {account}."))
            continue

        for path in files:
            if not is_valid_export_filename(path.name):
                _move_aside(path, FAILED_DIRNAME, FILENAME_REJECT_MESSAGE)
                results.append(InboxResult(account, path.name, "rejected", FILENAME_REJECT_MESSAGE))
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_INBOX_BYTES:
                _move_aside(path, FAILED_DIRNAME, f"Tệp {size / 1024 / 1024:.1f} MB, vượt giới hạn {MAX_INBOX_BYTES // 1024 // 1024} MB.")
                results.append(InboxResult(account, path.name, "rejected", "Tệp vượt giới hạn kích thước."))
                continue
            if not _is_stable(path, stable_delay):
                # Chưa đồng bộ xong; để nguyên, lượt quét sau sẽ gặp lại.
                results.append(InboxResult(account, path.name, "skipped", "Tệp đang được ghi, để lượt sau."))
                continue

            try:
                payload = path.read_bytes()
                rows = read_xlsx(path, account)
                summary: dict[str, Any] = import_rows(
                    engine,
                    filename=path.name,
                    file_bytes=payload,
                    account=account,
                    rows=rows,
                    uploaded_by_label="Thư mục nhập tự động",
                )
            except Exception as exc:  # noqa: BLE001 - tệp người dùng thả vào, lỗi gì cũng phải nói rõ
                _move_aside(path, FAILED_DIRNAME, f"Không nhập được: {exc}")
                results.append(InboxResult(account, path.name, "rejected", str(exc)))
                continue

            counts = {key: int(summary.get(key, 0)) for key in ("inserted", "updated", "unchanged", "rejected")}
            status = "duplicate" if summary.get("duplicate") else "imported"
            detail = ("Tệp này đã nhập trước đó." if status == "duplicate"
                      else f"thêm {counts['inserted']} · cập nhật {counts['updated']} · trùng {counts['unchanged']} · lỗi {counts['rejected']}")
            _move_aside(path, DONE_DIRNAME)
            results.append(InboxResult(account, path.name, status, detail, counts))

    return results
