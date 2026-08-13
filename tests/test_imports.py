from __future__ import annotations

import json

from datetime import date

import pytest
import pandas as pd
from sqlalchemy import select

from tiktok_affiliate_report.accounts import create_account
from tiktok_affiliate_report.db import get_engine, import_rows, init_db, monthly_targets, order_line_versions, raw_import_rows
from tiktok_affiliate_report.parser import EXPECTED_HEADERS, normalize_row
from tiktok_affiliate_report.reports import analytics, count_orders, daily_report, monthly_kpi, orders, overview, sheets_output


def raw_row(
    order="O1",
    sku="S1",
    gmv="100.000",
    status="Đã quyết toán",
    commission="10.000",
    account="CHIISTORE",
    order_date="01/03/2026 08:00:00",
    settlement_date="03/03/2026 08:00:00",
    product="Sản phẩm",
    product_id="P1",
    shop="Shop A",
    shop_id="SHOP1",
    content_type="Video",
    content_id="C1",
    currency="VND",
):
    row = {h: "/" for h in EXPECTED_HEADERS}
    row.update({
        "ID đơn hàng": order,
        "ID SKU": sku,
        "Tên sản phẩm": product,
        "ID sản phẩm": product_id,
        "Trạng thái quyết toán đơn hàng": status,
        "GMV": gmv,
        "Số món bán ra": "2",
        "Số món đã hoàn tiền": "1",
        "Tên cửa hàng": shop,
        "Mã cửa hàng": shop_id,
        "Loại nội dung": content_type,
        "Id nội dung": content_id,
        "Đơn vị tiền tệ": currency,
        "Tổng số tiền nhận được cuối cùng": "7.000",
        "Hoa hồng tiêu chuẩn ước tính": commission,
        "Hoa hồng Quảng cáo cửa hàng ước tính": "1.000",
        "Thưởng ước tính": "2.000",
        "Thưởng ước tính của đối tác liên kết": "3.000",
        "Ước tính phần chia doanh thu": "4.000",
        "Ngày đặt hàng": order_date,
        "Ngày quyết toán hoa hồng": settlement_date,
    })
    return normalize_row(row, account)


def engine():
    e = get_engine("sqlite:///:memory:")
    init_db(e)
    return e


def test_database_rejects_unknown_url_scheme():
    with pytest.raises(ValueError, match="sqlite:/// hoặc postgresql"):
        get_engine("not-a-sqlite-url")


def test_parser_rejected_rows_are_counted_but_do_not_block_the_import():
    e = engine()
    rows = [
        raw_row(order="O1") | {"_row_number": 2},
        {"_row_number": 3, "_rejected": {"row_number": 3, "reason": "Ngày đặt hàng: ngày '32/13/2026' không đúng định dạng"}},
        raw_row(order="O2") | {"_row_number": 4},
    ]

    result = import_rows(e, filename="mix.xlsx", file_bytes=b"mix", account="CHIISTORE", rows=rows)

    assert result["inserted"] == 2
    assert result["rejected"] == 1
    assert [item["row_number"] for item in result["rejected_rows"]] == [3]
    assert len(orders(e).index) == 2


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
    assert pd.isna(total["daily_target"])


def test_monthly_kpi_expands_daily_target_to_calendar_month():
    e = engine()
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])

    kpi = monthly_kpi(e)
    march = kpi[kpi["month"] == date(2026, 3, 1)]

    assert set(march["account"]) == {"ALL", "CHIISTORE"}
    total = march[march["account"] == "ALL"].iloc[0]
    assert pd.isna(total["daily_target"])
    assert pd.isna(total["monthly_target"])


def test_monthly_kpi_uses_selected_date_days_and_hides_combined_target_for_one_account():
    e = engine()
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])

    partial = monthly_kpi(e, start=date(2026, 3, 1), end=date(2026, 3, 3))
    total = partial[partial["account"] == "ALL"].iloc[0]
    assert total["days_in_scope"] == 3
    assert pd.isna(total["monthly_target"])

    one_account = monthly_kpi(e, accounts=["CHIISTORE"])
    assert one_account["daily_target"].isna().all()
    assert one_account["monthly_target"].isna().all()


def test_monthly_kpi_does_not_report_missing_imports_as_zero_actual():
    e = engine()

    kpi = monthly_kpi(e)
    assert kpi.empty


def test_monthly_kpi_combined_layer_includes_ineligible_without_touching_actual():
    # "Hiệu suất gộp": actual_commission phải giữ nguyên logic cũ (loại ineligible), trong khi
    # combined_commission phản ánh sức bán thật sự (gồm cả ineligible) để theo dõi riêng, không
    # được dùng làm số chính thức quyết định đã đạt mục tiêu hay chưa.
    e = engine()
    with e.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), daily_target_commission=1000))
    import_rows(
        e,
        filename="a.xlsx",
        file_bytes=b"a",
        account="CHIISTORE",
        rows=[
            raw_row(order="O1", sku="S1", gmv="100.000", commission="10.000"),
            raw_row(order="O2", sku="S2", gmv="50.000", status="Không đủ điều kiện", commission="5.000"),
        ],
    )

    kpi = monthly_kpi(e)
    row = kpi[(kpi["account"] == "CHIISTORE") & (kpi["month"] == date(2026, 3, 1))].iloc[0]

    assert row["actual_commission"] == 20000
    assert row["combined_commission"] == 35000
    assert row["ineligible_commission"] == 15000
    assert row["ineligible_rate"] == pytest.approx(15000 / 35000)
    assert row["monthly_target"] == 31000
    assert row["target_achievement"] == pytest.approx(20000 / 31000)
    assert row["combined_target_achievement"] == pytest.approx(35000 / 31000)
    assert row["combined_gap"] == 35000 - 31000


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
    assert pd.isna(middle["KPI/ngày"])
    assert pd.isna(middle["% đạt KPI"])

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


def test_five_thousand_rows_aggregate_exactly_like_source_math():
    """Ghi theo lô và lọc/phân trang ở SQL phải cho ra đúng con số như tính tay từ dữ liệu nguồn,
    kể cả khi vượt qua ranh giới lô 1.000 dòng và ranh giới tra cứu 500 khoá."""
    e = engine()
    size = 5000

    def gmv_of(index):
        return (100 + index) * 1000

    def commission_of(index):
        # raw_row cộng thêm 1.000 + 2.000 + 3.000 + 4.000 vào hoa hồng ước tính.
        return (10 + index % 7) * 1000 + 10000

    def ineligible(index):
        return index % 5 == 0

    rows = [
        raw_row(
            order=f"O{index}",
            sku=f"S{index}",
            gmv=f"{100 + index}.000",
            commission=f"{10 + index % 7}.000",
            status="Không đủ điều kiện" if ineligible(index) else "Đã quyết toán",
            order_date=f"{(index % 28) + 1:02d}/03/2026 08:00:00",
        )
        for index in range(size)
    ]

    result = import_rows(e, filename="big.xlsx", file_bytes=b"big", account="CHIISTORE", rows=rows)
    assert (result["inserted"], result["updated"], result["unchanged"], result["rejected"]) == (size, 0, 0, 0)

    total = overview(e).query("account == 'ALL'").iloc[0]
    assert total["orders"] == size
    assert total["gmv"] == sum(gmv_of(index) for index in range(size))
    assert total["actual_gmv"] == sum(gmv_of(index) for index in range(size) if not ineligible(index))
    assert total["actual_commission"] == sum(commission_of(index) for index in range(size) if not ineligible(index))
    assert total["cancelled_commission"] == sum(commission_of(index) for index in range(size) if ineligible(index))

    assert count_orders(e) == size
    assert count_orders(e, statuses=["ineligible"]) == len([index for index in range(size) if ineligible(index)])
    assert len(orders(e, limit=100, offset=0).index) == 100
    assert len(orders(e, limit=100, offset=size - 50).index) == 50
    assert len(orders(e, search="O4999").index) == 1

    # Nhập lại: 1.200 dòng đổi giá trị (vượt ranh giới lô), phần còn lại giữ nguyên.
    changed = [
        raw_row(
            order=f"O{index}",
            sku=f"S{index}",
            gmv=f"{500 + index}.000" if index < 1200 else f"{100 + index}.000",
            commission=f"{10 + index % 7}.000",
            status="Không đủ điều kiện" if ineligible(index) else "Đã quyết toán",
            order_date=f"{(index % 28) + 1:02d}/03/2026 08:00:00",
        )
        for index in range(size)
    ]
    again = import_rows(e, filename="big2.xlsx", file_bytes=b"big2", account="CHIISTORE", rows=changed)

    assert (again["inserted"], again["updated"], again["unchanged"], again["rejected"]) == (0, 1200, 3800, 0)
    assert count_orders(e) == size
    after = overview(e).query("account == 'ALL'").iloc[0]
    assert after["gmv"] == sum((500 + index) * 1000 if index < 1200 else gmv_of(index) for index in range(size))


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
    assert "THAOBRA - Tổng DT" not in output.columns
    assert output.iloc[0]["Tổng HH thực tế"] == 20000
    assert pd.isna(output.iloc[0]["% đạt KPI"])
    assert daily_report(e).query("account == 'ALL'").iloc[0]["orders"] == 2


def test_empty_account_allowlist_never_falls_back_to_all_accounts():
    e = engine()
    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])

    assert overview(e, accounts=[]).empty
    assert daily_report(e, accounts=[]).empty
    assert orders(e, accounts=[]).empty
    assert sheets_output(e, accounts=[]).empty


def test_analytics_returns_finance_dimensions_settlement_quality_and_forecast():
    e = engine()
    create_account(e, "CHIISTORE", display_name="Chii Store")
    create_account(e, "EMLINHNOIY", display_name="Em Linh")
    with e.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), daily_target_commission=1000))
    import_rows(
        e,
        filename="march.xlsx",
        file_bytes=b"march",
        account="CHIISTORE",
        rows=[
            raw_row(order="O1", product="Áo A", product_id="P1"),
            raw_row(
                order="O2",
                sku="S2",
                gmv="50.000",
                commission="5.000",
                status="Đang chờ",
                order_date="05/03/2026 08:00:00",
                settlement_date="/",
                product="Áo A",
                product_id="P1",
            ),
            raw_row(
                order="O3",
                sku="S3",
                gmv="25.000",
                commission="2.000",
                status="Không đủ điều kiện",
                order_date="06/03/2026 08:00:00",
                settlement_date="/",
                product="Quần B",
                product_id="P2",
            ),
        ],
    )
    import_rows(
        e,
        filename="february.xlsx",
        file_bytes=b"february",
        account="CHIISTORE",
        rows=[raw_row(order="O0", sku="S0", order_date="01/02/2026 08:00:00")],
    )

    result = analytics(
        e,
        accounts=["CHIISTORE"],
        start=date(2026, 3, 1),
        end=date(2026, 3, 31),
        today=date(2026, 3, 10),
    )

    assert result["summary"]["orders"] == 3
    assert result["summary"]["gross_gmv"] == 175000
    assert result["summary"]["actual_gmv"] == 150000
    assert result["summary"]["actual_commission"] == 35000
    assert result["previous_period"]["summary"]["orders"] == 1
    assert {row["status"] for row in result["status_breakdown"]} == {"settled", "pending", "ineligible"}
    ineligible_row = next(row for row in result["status_breakdown"] if row["status"] == "ineligible")
    # actual_commission == 0 là đúng thiết kế (đơn ineligible không tính vào tổng thực tế), nhưng
    # initial_commission phải giữ nguyên giá trị ước tính thô — không được zero-out theo, nếu
    # không UI sẽ hiện "0" cho toàn bộ nhóm ineligible dù file gốc có số liệu.
    assert ineligible_row["actual_commission"] == 0
    assert ineligible_row["initial_commission"] == 12000
    assert result["account_breakdown"][0]["commission_share"] == 1
    assert result["products"][0]["id"] == "P1"
    assert next(row for row in result["products"] if row["id"] == "P2")["cancellation_rate"] == 1
    assert result["content"][0]["id"] == "C1"
    assert result["settlement"]["median_lag_days"] == 2
    assert result["settlement"]["pending_aging"][0] == {"bucket": "0-7", "count": 1}
    assert result["data_quality"]["import_batches"] == 2
    # Hai dòng này chưa quyết toán nên TikTok để trống ngày — bình thường, không phải dữ liệu
    # bẩn. Giao diện đếm chúng là "vấn đề" cho tới v2.0.24; nay chỉ đơn ĐÃ quyết toán mà vẫn
    # thiếu ngày mới bị coi là bất thường.
    assert result["data_quality"]["missing_settlement_date_rows"] == 2
    assert result["data_quality"]["settled_missing_settlement_rows"] == 0
    assert result["target"]["monthly_target"] == 31000
    assert result["target"]["projected_month_end"] == 108500


def test_khong_luu_trung_chuoi_json_goc_o_order_line_versions():
    """Chuỗi JSON gốc chỉ nằm một chỗ: raw_import_rows.

    Đo trên database thật: bản sao thứ hai ở order_line_versions chiếm 12,8 MB trên 45,7 MB,
    200/200 cặp giống hệt nhau từng byte, và không nơi nào trong mã đọc nó. Trả default="" ở
    db.py về việc ghi lại `raw` thì test này ĐỎ.
    """
    e = engine()

    import_rows(e, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])

    with e.connect() as conn:
        version = conn.execute(select(order_line_versions)).mappings().one()
        goc = conn.execute(select(raw_import_rows.c.raw_json)).scalar_one()
    assert version["raw_json"] == ""
    # Bản gốc phải còn nguyên, vì hoàn tác lần nhập và audit đều dựa vào nó. So sánh sau khi
    # đưa qua JSON vì hai trường ngày được lưu thành chuỗi, phần còn lại giữ nguyên từng trường.
    assert goc == json.loads(json.dumps(raw_row(), default=str))


def test_dong_bi_tu_choi_khong_thuoc_ve_ky_nao():
    """import_* là số toàn thời gian, và điều đó là cố ý.

    Từng có ý định lọc import_batches theo khoảng ngày đang xem cho "gọn". Nhưng bộ lọc trên
    trang lọc theo NGÀY ĐẶT ĐƠN, còn created_at là LÚC NHẬP TỆP — nhập dữ liệu tháng 3 vào
    tháng 8 là chuyện thường, lọc như vậy sẽ giấu mất chính lần nhập đã tạo ra dữ liệu đang xem.
    Riêng dòng bị từ chối thì còn không có ngày đặt đơn nào cả vì chúng chưa từng đọc được.
    Giao diện vì thế phải hiện chúng riêng kèm nhãn "từ trước tới nay".
    """
    from tiktok_affiliate_report.reports import analytics

    e = engine()
    import_rows(
        e,
        filename="mix.xlsx",
        file_bytes=b"mix",
        account="CHIISTORE",
        rows=[
            raw_row(order="O1", sku="S1") | {"_row_number": 2},
            {"_row_number": 3, "_rejected": {"row_number": 3, "reason": "ngày sai định dạng"}},
        ],
    )

    thang_ba = analytics(e, start=date(2026, 3, 1), end=date(2026, 3, 31))
    thang_nam = analytics(e, start=date(2026, 5, 1), end=date(2026, 5, 31))

    # Cùng một con số ở mọi phạm vi: nó không thuộc về kỳ nào.
    assert thang_ba["data_quality"]["import_rejected"] == 1
    assert thang_nam["data_quality"]["import_rejected"] == 1
    # Còn chỉ số theo kỳ thì đúng là rỗng ở tháng không có đơn nào.
    assert thang_nam["summary"]["orders"] == 0
