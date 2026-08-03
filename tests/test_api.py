from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

import tiktok_affiliate_report.api as api_module
from tiktok_affiliate_report.api import create_app
from tiktok_affiliate_report.db import get_engine, import_rows
from tiktok_affiliate_report.parser import EXPECTED_HEADERS, normalize_row


def api(tmp_path):
    engine = get_engine(f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    return TestClient(
        create_app(engine),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    ), engine


def raw_export_row(**updates):
    row = {header: "/" for header in EXPECTED_HEADERS}
    row.update({
        "ID đơn hàng": "O1",
        "ID SKU": "S1",
        "Tên sản phẩm": "Sản phẩm",
        "Trạng thái quyết toán đơn hàng": "Đã quyết toán",
        "GMV": "100.000",
        "Số món bán ra": "2",
        "Số món đã hoàn tiền": "1",
        "Tên cửa hàng": "Shop A",
        "Tổng số tiền nhận được cuối cùng": "7.000",
        "Hoa hồng tiêu chuẩn ước tính": "10.000",
        "Hoa hồng Quảng cáo cửa hàng ước tính": "1.000",
        "Thưởng ước tính": "2.000",
        "Thưởng ước tính của đối tác liên kết": "3.000",
        "Ước tính phần chia doanh thu": "4.000",
        "Ngày đặt hàng": "01/03/2026 08:00:00",
    })
    row.update(updates)
    return row


def normalized(account="CHIISTORE", **updates):
    return normalize_row(raw_export_row(**updates), account)


def xlsx_bytes(rows):
    buf = BytesIO()
    pd.DataFrame(rows, columns=EXPECTED_HEADERS).to_excel(buf, index=False)
    return buf.getvalue()


def test_health_and_meta(tmp_path):
    client, _ = api(tmp_path)

    assert client.get("/health").json() == {"status": "ok"}
    meta = client.get("/api/v1/meta").json()

    assert meta["accounts"] == ["CHIISTORE", "EMLINHNOIY", "THAOBRA"]
    assert meta["statuses"] == ["settled", "ineligible", "pending", "unknown"]
    assert meta["max_upload_mb"] == 20


def test_report_endpoints_return_items_count_and_safe_nulls(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])

    overview = client.get("/api/v1/overview", params={"account": "CHIISTORE"}).json()
    daily = client.get("/api/v1/daily", params={"start": "2026-03-01", "end": "2026-03-01"}).json()
    monthly = client.get("/api/v1/monthly-kpi", params={"month": "2026-04"}).json()

    assert overview["count"] == len(overview["items"]) == 2
    assert {item["account"] for item in overview["items"]} == {"CHIISTORE", "ALL"}
    assert daily["count"] == len(daily["items"])
    assert daily["items"][0]["day"] == "2026-03-01"
    assert monthly["count"] == 1
    assert monthly["items"][0]["actual_commission"] is None


def test_orders_paginates_with_total(tmp_path):
    client, engine = api(tmp_path)
    import_rows(
        engine,
        filename="many.xlsx",
        file_bytes=b"many",
        account="CHIISTORE",
        rows=[normalized(**{"ID đơn hàng": f"O{index}", "ID SKU": f"S{index}"}) for index in range(3)],
    )

    payload = client.get("/api/v1/orders", params={"limit": 2, "offset": 1, "search": "O"}).json()

    assert payload["count"] == 2
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert len(payload["items"]) == 2


def test_import_requires_account_and_imports_xlsx(tmp_path):
    client, _ = api(tmp_path)
    data = xlsx_bytes([raw_export_row()])

    missing = client.post("/api/v1/imports", files={"file": ("orders.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    unknown = client.post(
        "/api/v1/imports",
        data={"account": "NOT_ALLOWED"},
        files={"file": ("orders.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    wrong_type = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("orders.csv", data, "text/csv")},
    )
    created = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("orders.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    duplicate = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("orders-copy.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert missing.status_code == 422
    assert unknown.status_code == 422
    assert wrong_type.status_code == 415
    assert created.status_code == 200
    assert created.json() | {"batch_id": created.json()["batch_id"]} == {
        "batch_id": created.json()["batch_id"],
        "duplicate": False,
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
        "rejected_rows": [],
    }
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["inserted"] == 0


def test_import_rejects_file_when_stream_crosses_size_limit(tmp_path, monkeypatch):
    client, _ = api(tmp_path)
    monkeypatch.setattr(api_module, "MAX_UPLOAD_MB", 0)

    response = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("orders.xlsx", b"x", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "File exceeds 0 MB"}
