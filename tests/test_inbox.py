from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_api import raw_export_row  # noqa: E402

from affiliate_report import inbox  # noqa: E402
from affiliate_report.accounts import create_account  # noqa: E402
from affiliate_report.db import get_engine, init_db  # noqa: E402
from affiliate_report.parser import EXPECTED_HEADERS  # noqa: E402


def _engine(tmp_path: Path):
    engine = get_engine(f"sqlite:///{(tmp_path / 'inbox.db').as_posix()}")
    init_db(engine)
    create_account(engine, "SHOTSHOP", display_name="SHOTSHOP")
    return engine


def _xlsx_bytes(order_id: str = "O1") -> bytes:
    buf = BytesIO()
    pd.DataFrame([raw_export_row(**{"ID đơn hàng": order_id})], columns=EXPECTED_HEADERS).to_excel(buf, index=False)
    return buf.getvalue()


def _drop(root: Path, account: str, name: str, payload: bytes) -> Path:
    folder = root / account
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(payload)
    return path


def test_file_dropped_into_the_account_folder_is_imported_and_filed_away(tmp_path):
    engine = _engine(tmp_path)
    data_dir = tmp_path / "data"
    root = inbox.ensure_inbox(data_dir, ["SHOTSHOP"])
    path = _drop(root, "SHOTSHOP", "affiliate_orders.xlsx", _xlsx_bytes())

    results = inbox.scan_inbox(engine, data_dir, stable_delay=0)

    assert [r.status for r in results] == ["imported"]
    assert results[0].counts["inserted"] == 1
    assert not path.exists(), "tệp đã nhập phải được dời đi để lượt sau không nhập lại"
    assert (root / "SHOTSHOP" / inbox.DONE_DIRNAME / "affiliate_orders.xlsx").is_file()


def test_the_same_file_dropped_twice_does_not_double_count(tmp_path):
    """import_rows băm nội dung tệp, nên thả lại đúng tệp cũ chỉ là 'đã nhập trước đó'."""
    engine = _engine(tmp_path)
    data_dir = tmp_path / "data"
    root = inbox.ensure_inbox(data_dir, ["SHOTSHOP"])
    payload = _xlsx_bytes()

    _drop(root, "SHOTSHOP", "affiliate_orders.xlsx", payload)
    first = inbox.scan_inbox(engine, data_dir, stable_delay=0)
    _drop(root, "SHOTSHOP", "affiliate_orders.xlsx", payload)
    second = inbox.scan_inbox(engine, data_dir, stable_delay=0)

    assert first[0].status == "imported"
    assert second[0].status == "duplicate"


def test_a_half_synced_file_is_left_for_the_next_pass(tmp_path, monkeypatch):
    """Dịch vụ đồng bộ ghi tệp dần dần. Nhập nửa tệp cho ra dữ liệu rác chứ không báo lỗi rõ,
    nên tệp còn đang lớn lên phải bị bỏ qua chứ không phải đọc đại.

    Giả lập đúng cơ chế thật: tệp lớn thêm trong lúc _is_stable đang chờ giữa hai lần nhìn.
    """
    engine = _engine(tmp_path)
    data_dir = tmp_path / "data"
    root = inbox.ensure_inbox(data_dir, ["SHOTSHOP"])
    path = _drop(root, "SHOTSHOP", "affiliate_orders_dang-tai.xlsx", b"MOT-NUA-TEP")

    def grow_while_waiting(_seconds):
        path.write_bytes(path.read_bytes() + b"-THEM-DU-LIEU")

    monkeypatch.setattr(inbox.time, "sleep", grow_while_waiting)
    results = inbox.scan_inbox(engine, data_dir)

    assert [r.status for r in results] == ["skipped"]
    assert path.exists(), "tệp chưa ghi xong phải được để nguyên chờ lượt sau"
    assert not (root / "SHOTSHOP" / inbox.DONE_DIRNAME).exists()


def test_folder_for_an_unknown_account_is_reported_not_silently_ignored(tmp_path):
    engine = _engine(tmp_path)
    data_dir = tmp_path / "data"
    root = inbox.ensure_inbox(data_dir, ["SHOTSHOP"])
    _drop(root, "KHONGTONTAI", "orders.xlsx", _xlsx_bytes())

    results = inbox.scan_inbox(engine, data_dir, stable_delay=0)

    assert [r.status for r in results] == ["rejected"]
    assert "KHONGTONTAI" in results[0].detail
    assert (root / "KHONGTONTAI" / inbox.FAILED_DIRNAME / "orders.xlsx").is_file()


def test_a_corrupt_file_is_filed_with_a_readable_reason(tmp_path):
    engine = _engine(tmp_path)
    data_dir = tmp_path / "data"
    root = inbox.ensure_inbox(data_dir, ["SHOTSHOP"])
    _drop(root, "SHOTSHOP", "affiliate_orders_hong.xlsx", b"day khong phai excel")

    results = inbox.scan_inbox(engine, data_dir, stable_delay=0)

    assert [r.status for r in results] == ["rejected"]
    failed = root / "SHOTSHOP" / inbox.FAILED_DIRNAME
    assert (failed / "affiliate_orders_hong.xlsx").is_file()
    note = (failed / "affiliate_orders_hong.xlsx.txt").read_text(encoding="utf-8")
    assert "Không nhập được" in note


def test_a_file_with_the_wrong_name_is_rejected_not_silently_ignored(tmp_path):
    """Thư mục Download trên điện thoại lẫn đủ loại tệp khác; chỉ tên bắt đầu affiliate_orders
    mới được nhận (xem parser.FILENAME_PATTERN), tệp khác phải báo rõ lý do như mọi rejection khác
    trong module này chứ không lặng lẽ bỏ qua."""
    engine = _engine(tmp_path)
    data_dir = tmp_path / "data"
    root = inbox.ensure_inbox(data_dir, ["SHOTSHOP"])
    _drop(root, "SHOTSHOP", "bao-cao-thang.xlsx", _xlsx_bytes())

    results = inbox.scan_inbox(engine, data_dir, stable_delay=0)

    assert [r.status for r in results] == ["rejected"]
    assert "affiliate_orders" in results[0].detail
    assert (root / "SHOTSHOP" / inbox.FAILED_DIRNAME / "bao-cao-thang.xlsx").is_file()


def test_scan_is_a_no_op_when_the_inbox_was_never_created(tmp_path):
    engine = _engine(tmp_path)
    assert inbox.scan_inbox(engine, tmp_path / "data", stable_delay=0) == []
