from __future__ import annotations

from datetime import date

import pytest
import pandas as pd
from sqlalchemy import select

from tiktok_affiliate_report.db import get_engine, import_rows, init_db, order_line_versions
from tiktok_affiliate_report.parser import EXPECTED_HEADERS, normalize_row
from tiktok_affiliate_report.reports import daily_report, monthly_kpi, orders, overview, sheets_output


def raw_row(
    order="O1",
    sku="S1",
    gmv="100.000",
    status="Đã quyết toán",
    commission="10.000",
    account="CHIISTORE",
    order_date="01/03/2026 08:00:00",
):
    row = {h: "/" for h in EXPECTED_HEADERS}
    row.update({
        "ID đơn hàng": order,
        "ID SKU": sku,
        "Tên sản phẩm": "Sản phẩm",
        "Trạng thái quyết toán đơn hàng": status,
        "GMV": gmv,
        "Số món bán ra": "2",
        "Số món đã hoàn tiền": "1",
        "Tên cửa hàng": "Shop A",
        "Tổng số tiền nhận được cuối cùng": "7.000",
        "Hoa hồng tiêu chuẩn ước tính": commission,
        "Hoa hồng Quảng cáo cửa hàng ước tính": "1.000",
        "Thưởng ước tính": "2.000",
        "Thưởng ước tính của đối tác liên kết": "3.000",
        "Ước tính phần chia doanh thu": "4.000",
        "Ngày đặt hàng": order_date,
    })
    return normalize_row(row, account)


def engine():
    e = get_engine("sqlite:///:memory:")
    init_db(e)
    return e


def test_database_rejects_unknown_url_scheme():
    with pytest.raises(ValueError, match="sqlite:/// hoặc postgresql"):
        get_engine("not-a-sqlite-url")


def test_duplicate_file_sha_is_noop():
    e = engine()
    rows = [raw_row()]

    first = import_rows(e, filename="a.xlsx", file_bytes=b"same", account="CHIISTORE", rows=rows)
    second = import_rows(e, filename="a-copy.xlsx", file_bytes=b"same", account="CHIISTORE", rows=rows)

    assert first["inserted"] == 1
    assert second == {"batch_id": first["batch_id"], "duplicate": True, "inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0}


def test_file_hash_is_scoped_to_affiliate_account():
    e = engine()
    chii = [raw_row()]
    emlinh = [normalize_row({**{h: "/" for h in EXPECTED_HEADERS}, **{
        "ID đơn hàng": "O1",
        "ID SKU": "S1",
        "Trạng thái quyết toán đơn hàng": "Đã quyết toán",
    }}, "EMLINHNOIY")]

    first = import_rows(e, filename="a.xlsx", file_bytes=b"same", account="CHIISTORE", rows=chii)
    second = import_rows(e, filename="a.xlsx", file_bytes=b"same", account="EMLINHNOIY", rows=emlinh)

    assert first["inserted"] == 1
    assert second["inserted"] == 1


def test_same_business_key_same_hash_is_unchanged_on_new_file():
    e = engine()
    rows = [raw_row()]

    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=rows)
    result = import_rows(e, filename="b.xlsx", file_bytes=b"b", account="CHIISTORE", rows=rows)

    assert result["unchanged"] == 1
    with e.connect() as conn:
        versions = conn.execute(select(order_line_versions)).all()
    assert len(versions) == 1


def test_changed_row_creates_new_current_version():
    e = engine()

    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row(gmv="100.000")])
    result = import_rows(e, filename="b.xlsx", file_bytes=b"b", account="CHIISTORE", rows=[raw_row(gmv="200.000")])

    assert result["updated"] == 1
    with e.connect() as conn:
        rows = conn.execute(select(order_line_versions).order_by(order_line_versions.c.version)).mappings().all()
    assert [r["version"] for r in rows] == [1, 2]
    assert [r["is_current"] for r in rows] == [False, True]
    assert rows[-1]["gmv"] == 200000
    assert rows[-1]["units_sold"] == 2
    assert rows[-1]["units_refunded"] == 1
    assert rows[-1]["final_received"] == 7000


def test_same_batch_conflicting_business_key_is_rejected_before_import():
    e = engine()

    with pytest.raises(ValueError, match="business key trùng"):
        import_rows(
            e,
            filename="collision.xlsx",
            file_bytes=b"collision",
            account="CHIISTORE",
            rows=[raw_row(gmv="100.000"), raw_row(gmv="200.000")],
        )

    with e.connect() as conn:
        assert conn.execute(select(order_line_versions)).all() == []


def test_daily_aggregation_uses_current_rows_and_ineligible_cancellations():
    e = engine()
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row(order="O1", sku="S1", gmv="100.000", commission="10.000")])
    import_rows(e, filename="b.xlsx", file_bytes=b"b", account="CHIISTORE", rows=[raw_row(order="O2", sku="S2", gmv="50.000", status="Không đủ điều kiện", commission="5.000")])
    import_rows(e, filename="c.xlsx", file_bytes=b"c", account="CHIISTORE", rows=[raw_row(order="O1", sku="S1", gmv="120.000", commission="12.000")])

    report = daily_report(e)

    assert set(report["account"]) == {"ALL", "CHIISTORE"}
    row = report[report["account"] == "CHIISTORE"].iloc[0].to_dict()
    assert row["orders"] == 2
    assert row["gross_gmv"] == 170000
    assert row["initial_commission"] == 37000  # (12k + four extras) + (5k + four extras)
    assert row["cancelled_rows"] == 1
    assert row["cancelled_gmv"] == 50000
    assert row["actual_gmv"] == 120000
    assert row["actual_commission"] == 22000

    total = report[report["account"] == "ALL"].iloc[0].to_dict()
    assert total["actual_commission"] == 22000
    assert total["daily_target"] == 350000


def test_monthly_kpi_expands_daily_target_to_calendar_month():
    e = engine()
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])

    kpi = monthly_kpi(e)
    march = kpi[kpi["month"] == date(2026, 3, 1)]

    assert len(march) == 1
    assert march.iloc[0]["daily_target"] == 350000
    assert march.iloc[0]["monthly_target"] == 350000 * 31


def test_monthly_kpi_uses_selected_date_days_and_hides_combined_target_for_one_account():
    e = engine()
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])

    partial = monthly_kpi(e, start=date(2026, 3, 1), end=date(2026, 3, 3))
    assert partial.iloc[0]["days_in_scope"] == 3
    assert partial.iloc[0]["monthly_target"] == 350000 * 3

    one_account = monthly_kpi(e, accounts=["CHIISTORE"])
    assert pd.isna(one_account.iloc[0]["daily_target"])
    assert pd.isna(one_account.iloc[0]["monthly_target"])


def test_monthly_kpi_does_not_report_missing_imports_as_zero_actual():
    e = engine()

    kpi = monthly_kpi(e)
    march = kpi[kpi["month"] == date(2026, 3, 1)].iloc[0]

    assert march["order_lines"] == 0
    assert pd.isna(march["actual_commission"])
    assert pd.isna(march["gap"])
    assert pd.isna(march["target_achievement"])


def test_google_sheets_output_fills_calendar_gaps_and_missing_kpi_is_blank():
    e = engine()
    import_rows(
        e,
        filename="march.xlsx",
        file_bytes=b"march",
        account="CHIISTORE",
        rows=[
            raw_row(order="O1", order_date="01/03/2026 08:00:00"),
            raw_row(order="O2", order_date="03/03/2026 08:00:00"),
        ],
    )

    output = sheets_output(e, start=date(2026, 3, 1), end=date(2026, 3, 3))
    assert output["Ngày"].tolist() == ["2026-03-01", "2026-03-02", "2026-03-03"]
    middle = output.iloc[1]
    assert middle["Tổng DT thực tế"] == 0
    assert middle["KPI/ngày"] == 350000
    assert middle["% đạt KPI"] == 0

    import_rows(
        e,
        filename="future.xlsx",
        file_bytes=b"future",
        account="CHIISTORE",
        rows=[raw_row(order="O3", order_date="01/01/2027 08:00:00")],
    )
    future = daily_report(e, start=date(2027, 1, 1), end=date(2027, 1, 1)).query("account == 'ALL'").iloc[0]
    assert pd.isna(future["daily_target"])
    assert pd.isna(future["target_achievement"])


def test_orders_returns_every_match_for_full_csv_export():
    e = engine()
    rows = [raw_row(order=f"O{index}", sku=f"S{index}") for index in range(1001)]
    import_rows(e, filename="many.xlsx", file_bytes=b"many", account="CHIISTORE", rows=rows)

    assert len(orders(e)) == 1001


def test_overview_all_and_google_sheets_output_keep_accounts_separate():
    e = engine()
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])
    import_rows(
        e,
        filename="b.xlsx",
        file_bytes=b"b",
        account="EMLINHNOIY",
        rows=[raw_row(gmv="50.000", status="Không đủ điều kiện", commission="5.000", account="EMLINHNOIY")],
    )

    total = overview(e).query("account == 'ALL'").iloc[0]
    assert total["orders"] == 2
    assert total["actual_gmv"] == 100000
    assert total["actual_commission"] == 20000

    output = sheets_output(e)
    assert list(output.columns[:3]) == ["Ngày", "CHIISTORE - Số lượng bán", "CHIISTORE - Tổng DT"]
    assert output.iloc[0]["CHIISTORE - HH thực tế"] == 20000
    assert output.iloc[0]["EMLINHNOIY - DT huỷ"] == 50000
    assert output.iloc[0]["THAOBRA - Tổng DT"] == 0
    assert output.iloc[0]["Tổng HH thực tế"] == 20000
    assert output.iloc[0]["% đạt KPI"] == pytest.approx(20000 / 350000)
    assert daily_report(e).query("account == 'ALL'").iloc[0]["orders"] == 2


def test_empty_account_allowlist_never_falls_back_to_all_accounts():
    e = engine()
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])

    assert overview(e, accounts=[]).empty
    assert daily_report(e, accounts=[]).empty
    assert orders(e, accounts=[]).empty
    assert sheets_output(e, accounts=[]).empty
