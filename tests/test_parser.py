from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from affiliate_report.parser import EXPECTED_HEADERS, normalize_row, normalize_status, parse_date, parse_int, read_xlsx


def raw_row(**overrides):
    row = {h: "/" for h in EXPECTED_HEADERS}
    row.update({
        "ID đơn hàng": "1234567890123456789",
        "ID SKU": "9876543210987654321",
        "Tên sản phẩm": "Áo thun",
        "Trạng thái quyết toán đơn hàng": "Không đủ điều kiện",
        "GMV": "234.900",
        "Số món bán ra": "2",
        "Số món đã hoàn tiền": "1",
        "Tên cửa hàng": "Shop A",
        "Tổng số tiền nhận được cuối cùng": "9.000",
        "Hoa hồng tiêu chuẩn ước tính": "1.000",
        "Hoa hồng Quảng cáo cửa hàng ước tính": "2.000",
        "Thưởng ước tính": "3.000",
        "Thưởng ước tính của đối tác liên kết": "4.000",
        "Ước tính phần chia doanh thu": "5.000",
        "Ngày đặt hàng": "12/03/2026 09:10:11",
    })
    row.update(overrides)
    return row


def test_parse_money_date_status_and_long_ids():
    row = normalize_row(raw_row(), "CHIISTORE")

    assert row["ID đơn hàng"] == "1234567890123456789"
    assert row["ID SKU"] == "9876543210987654321"
    assert parse_int("234.900") == 234900
    assert parse_date("12/03/2026 09:10:11").year == 2026
    assert row["GMV"] == 234900
    assert row["estimated_commission"] == 15000
    assert row["units_sold"] == 2
    assert row["units_refunded"] == 1
    assert row["final_received"] == 9000
    assert row["shop_name"] == "Shop A"
    assert row["status"] == "ineligible"
    assert row["Ngày quyết toán hoa hồng"] is None


def test_read_xlsx_requires_exact_47_headers():
    buf = BytesIO()
    pd.DataFrame([raw_row()]).to_excel(buf, index=False)
    buf.seek(0)

    rows = read_xlsx(buf, "EMLINHNOIY")

    assert len(rows) == 1
    assert rows[0]["account"] == "EMLINHNOIY"

    bad = BytesIO()
    pd.DataFrame([{"ID đơn hàng": "1"}]).to_excel(bad, index=False)
    bad.seek(0)
    with pytest.raises(ValueError, match="47 cột"):
        read_xlsx(bad, "EMLINHNOIY")


def test_read_xlsx_rejects_bad_rows_without_losing_the_file():
    buf = BytesIO()
    pd.DataFrame([
        raw_row(),
        raw_row(**{"Ngày đặt hàng": "32/13/2026 99:99:99"}),
        raw_row(**{"ID SKU": "/"}),
    ]).to_excel(buf, index=False)
    buf.seek(0)

    rows = read_xlsx(buf, "CHIISTORE")

    good = [row for row in rows if not row.get("_rejected")]
    bad = [row["_rejected"] for row in rows if row.get("_rejected")]
    assert len(good) == 1
    assert good[0]["_row_number"] == 2
    assert [item["row_number"] for item in bad] == [3, 4]
    assert "Ngày đặt hàng" in bad[0]["reason"]
    assert "ID SKU" in bad[1]["reason"]


def test_read_xlsx_accepts_reordered_and_extra_columns():
    source = raw_row()
    shuffled = {header: source[header] for header in reversed(EXPECTED_HEADERS)}
    shuffled["Cột TikTok mới thêm"] = "x"
    buf = BytesIO()
    pd.DataFrame([shuffled]).to_excel(buf, index=False)
    buf.seek(0)

    with pytest.warns(UserWarning, match="cột lạ"):
        rows = read_xlsx(buf, "CHIISTORE")

    assert len(rows) == 1
    assert rows[0]["ID SKU"] == "9876543210987654321"
    assert rows[0]["estimated_commission"] == 15000
    assert rows[0]["_raw"]["Cột TikTok mới thêm"] == "x"


def test_tiktok_pending_status_variants():
    assert normalize_status("AwaitingPayment") == "pending"
    assert normalize_status("Chờ xử lý") == "pending"
    assert normalize_status("Chờ thanh toán") == "pending"


def test_final_received_keeps_missing_distinct_from_zero():
    row = normalize_row(raw_row(**{"Tổng số tiền nhận được cuối cùng": "/"}), "CHIISTORE")

    assert row["final_received"] is None


def test_read_xlsx_rejects_excessive_row_count(monkeypatch):
    class OversizedSheet:
        def __len__(self):
            return 50_001

    monkeypatch.setattr("affiliate_report.parser.pd.read_excel", lambda *args, **kwargs: OversizedSheet())

    with pytest.raises(ValueError, match="50,000"):
        read_xlsx(BytesIO(), "CHIISTORE")
