from __future__ import annotations

import pytest

from affiliate_report.accounts import create_account
from affiliate_report.db import get_engine, import_rows, init_db
from affiliate_report.imports import order_line_history, undo_import, undo_preview
from affiliate_report.parser import EXPECTED_HEADERS, normalize_row
from affiliate_report.reports import orders, overview


def raw_row(order="O1", sku="S1", gmv="100.000", commission="10.000", account="CHIISTORE", status="Đã quyết toán"):
    row = {header: "/" for header in EXPECTED_HEADERS}
    row.update({
        "ID đơn hàng": order,
        "ID SKU": sku,
        "Tên sản phẩm": "Sản phẩm",
        "Trạng thái quyết toán đơn hàng": status,
        "GMV": gmv,
        "Số món bán ra": "2",
        "Số món đã hoàn tiền": "0",
        "Tên cửa hàng": "Shop A",
        "Hoa hồng tiêu chuẩn ước tính": commission,
        "Ngày đặt hàng": "01/03/2026 08:00:00",
    })
    return normalize_row(row, account)


def engine(tmp_path):
    e = get_engine(f"sqlite:///{(tmp_path / 'undo.db').as_posix()}")
    init_db(e)
    create_account(e, "CHIISTORE")
    return e


def snapshot(e):
    total = overview(e).query("account == 'ALL'").iloc[0]
    return {
        "orders": int(total["orders"]),
        "gmv": int(total["gmv"]),
        "actual_commission": int(total["actual_commission"]),
        "lines": len(orders(e).index),
    }


def test_undo_returns_data_to_the_state_after_the_earlier_import(tmp_path):
    e = engine(tmp_path)
    first = import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[
        raw_row(order="O1", sku="S1", gmv="100.000", commission="10.000"),
        raw_row(order="O2", sku="S2", gmv="200.000", commission="20.000"),
    ])
    after_first = snapshot(e)

    second = import_rows(e, filename="b.xlsx", file_bytes=b"b", account="CHIISTORE", rows=[
        raw_row(order="O1", sku="S1", gmv="999.000", commission="99.000"),  # đè lên dòng cũ
        raw_row(order="O3", sku="S3", gmv="300.000", commission="30.000"),  # dòng hoàn toàn mới
    ])
    assert (second["inserted"], second["updated"]) == (1, 1)
    assert snapshot(e) != after_first

    preview = undo_preview(e, second["batch_id"])
    assert preview["is_latest"] is True
    assert preview["warning"] is None
    assert preview["removed_versions"] == 2
    assert preview["removed_lines"] == 1  # O3 biến mất hẳn
    assert preview["restored_lines"] == 1  # O1 quay lại phiên bản của lần nhập đầu

    result = undo_import(e, second["batch_id"], preview["confirmation"])

    assert (result["removed_lines"], result["restored_lines"]) == (1, 1)
    assert result["backup_path"] is not None
    assert snapshot(e) == after_first
    assert [item["version"] for item in order_line_history(e, "CHIISTORE|O1|S1")] == [1]
    assert order_line_history(e, "CHIISTORE|O3|S3") == []
    assert first["batch_id"] != second["batch_id"]


def test_undo_requires_the_exact_confirmation_phrase(tmp_path):
    e = engine(tmp_path)
    batch = import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])

    with pytest.raises(ValueError, match="HOAN TAC"):
        undo_import(e, batch["batch_id"], "HOAN TAC")

    assert snapshot(e)["lines"] == 1


def test_undo_of_an_older_import_warns_and_keeps_the_newer_import_in_charge(tmp_path):
    e = engine(tmp_path)
    older = import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[
        raw_row(order="O1", sku="S1", gmv="100.000"),
    ])
    import_rows(e, filename="b.xlsx", file_bytes=b"b", account="CHIISTORE", rows=[
        raw_row(order="O1", sku="S1", gmv="500.000"),
    ])
    newest = snapshot(e)

    preview = undo_preview(e, older["batch_id"])
    assert preview["is_latest"] is False
    assert preview["newer_batches"] == 1
    assert "mới hơn" in preview["warning"]
    assert preview["restored_lines"] == 0  # phiên bản của lần nhập cũ đã không còn là current

    undo_import(e, older["batch_id"], preview["confirmation"])

    assert snapshot(e) == newest
    history = order_line_history(e, "CHIISTORE|O1|S1")
    assert [item["version"] for item in history] == [2]
    assert history[0]["is_current"] is True


def test_order_line_history_shows_every_version_with_its_import(tmp_path):
    e = engine(tmp_path)
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row(gmv="100.000")])
    import_rows(e, filename="b.xlsx", file_bytes=b"b", account="CHIISTORE", rows=[raw_row(gmv="200.000")])

    history = order_line_history(e, "CHIISTORE|O1|S1")

    assert [item["version"] for item in history] == [2, 1]
    assert [item["is_current"] for item in history] == [True, False]
    assert [item["gmv"] for item in history] == [200000, 100000]
    assert [item["filename"] for item in history] == ["b.xlsx", "a.xlsx"]
