from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import date
from io import BytesIO
from urllib.parse import quote

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import select

import affiliate_report.api as api_module
import affiliate_report.reset_data as reset_data_module
from affiliate_report.accounts import create_account
from affiliate_report.api import create_app
from affiliate_report.db import (
    accounts,
    get_engine,
    import_batches,
    import_rows,
    monthly_targets,
    order_line_versions,
)
from affiliate_report.parser import EXPECTED_HEADERS, FILENAME_REJECT_MESSAGE, normalize_row
from affiliate_report.version import APP_VERSION


def api(tmp_path):
    engine = get_engine(f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    app = create_app(engine)
    for code in ("CHIISTORE", "EMLINHNOIY", "THAOBRA"):
        create_account(engine, code, display_name=code)
    return TestClient(
        app,
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

    assert client.app.version == APP_VERSION
    assert client.get("/health").json() == {"status": "ok", "app_version": APP_VERSION}
    meta = client.get("/api/v1/meta").json()

    assert meta["accounts"] == ["CHIISTORE", "EMLINHNOIY", "THAOBRA"]
    assert [item["code"] for item in meta["account_items"]] == meta["accounts"]
    assert meta["statuses"] == ["settled", "ineligible", "pending", "unknown"]
    assert meta["max_upload_mb"] == 20
    assert meta["capabilities"]["database_backend"] == "sqlite"
    assert meta["capabilities"]["data_admin"]["available"] is True
    assert meta["capabilities"]["update_check"]["available"] is True
    assert meta["identity_policy"] == {
        "mode": "local",
        "oidc_allowlist_enforced": False,
        "enforcement": "local_owner",
    }


def test_fresh_database_has_no_user_specific_accounts_or_targets(tmp_path):
    engine = get_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    client = TestClient(create_app(engine), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

    assert client.get("/api/v1/meta").json()["accounts"] == []
    assert client.get("/api/v1/targets").json()["items"] == []


def test_local_owner_can_check_and_schedule_verified_update(tmp_path, monkeypatch):
    client, _ = api(tmp_path)
    installer = tmp_path / "AffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"verified")
    bootstrap = tmp_path / "TikTokAffiliateUpdater-v1.0.0.ps1"
    bootstrap.write_bytes(b"bootstrap")
    scheduled = {}
    pending_workers = []

    monkeypatch.setattr(
        api_module,
        "check_for_update",
        lambda: {
            "current_version": APP_VERSION,
            "latest_version": "1.2.1",
            "available": True,
            "installable": True,
            "release_url": "https://github.com/example/release",
        },
    )
    monkeypatch.setattr(api_module, "_automatic_update_supported", lambda _app: True)
    monkeypatch.setattr(
        api_module,
        "download_latest_update",
        lambda _data_dir, progress_callback=None: {
            "version": "1.2.1",
            "installer_path": str(installer),
            "sha256": "A" * 64,
            "bootstrap_path": str(bootstrap),
            "bootstrap_sha256": "B" * 64,
            "bootstrap_protocol": 1,
            "bootstrap_version": "1.0.0",
            "release_url": "https://github.com/example/release",
        },
    )

    def capture_schedule(path, sha256, log_path, shutdown, **kwargs):
        scheduled.update(
            path=path,
            sha256=sha256,
            log_path=log_path,
            shutdown=shutdown,
            **kwargs,
        )

    monkeypatch.setattr(api_module, "schedule_installer", capture_schedule)
    monkeypatch.setattr(api_module, "_start_update_worker", pending_workers.append)
    client.app.state.update_shutdown = lambda: None

    checked = client.get("/api/v1/admin/update")
    wrong = client.post("/api/v1/admin/update/install", json={"confirmation": "UPDATE"})
    installed = client.post(
        "/api/v1/admin/update/install",
        json={"confirmation": "CAP NHAT UNG DUNG"},
    )
    duplicate = client.post(
        "/api/v1/admin/update/install",
        json={"confirmation": "CAP NHAT UNG DUNG"},
    )

    assert checked.status_code == 200
    assert checked.json()["automatic_install_supported"] is True
    assert wrong.status_code == 422
    assert installed.status_code == 200
    assert installed.json() == {
        "status": "started",
        "version": "1.2.1",
        "release_url": "https://github.com/example/release",
    }
    assert len(pending_workers) == 1
    pending_workers.pop()()
    assert scheduled["path"] == installer
    assert scheduled["sha256"] == "A" * 64
    assert scheduled["log_path"].name == "updater.log"
    assert scheduled["status_path"].name == "update-status.json"
    assert scheduled["target_version"] == "1.2.1"
    assert scheduled["bootstrap_path"] == bootstrap
    assert scheduled["bootstrap_sha256"] == "B" * 64
    assert scheduled["bootstrap_protocol"] == 1
    assert scheduled["bootstrap_version"] == "1.0.0"
    assert scheduled["installer_size"] == installer.stat().st_size
    assert scheduled["instance_state_path"].name == "instance.json"
    progress = client.get("/api/v1/admin/update/progress")
    assert progress.status_code == 200
    assert progress.json()["phase"] == "verifying"
    assert progress.json()["percent"] == 100.0
    assert duplicate.status_code == 409


def test_update_progress_hides_technical_error_and_returns_next_action(tmp_path):
    client, _ = api(tmp_path)
    status_path = tmp_path / "update-status.json"
    technical_error = r"Installer exited with code 5 at C:\Users\Administrator\AppData\Local\Temp\installer.exe"
    api_module.write_update_status(
        status_path,
        phase="failed",
        target_version="2.0.4",
        bytes_downloaded=100,
        bytes_total=100,
        error=technical_error,
    )

    response = client.get("/api/v1/admin/update/progress")

    assert response.status_code == 200
    assert response.json()["error"] == "Không thể hoàn tất cài đặt bản cập nhật."
    assert response.json()["error_action"] == "Bấm “Thử lại” để tải lại gói. Nếu lỗi tiếp diễn, hãy mở trang phát hành hoặc liên hệ người hỗ trợ."
    assert technical_error not in response.text
    assert json.loads(status_path.read_text(encoding="utf-8"))["error"] == technical_error


def test_installed_local_owner_can_shutdown_app(tmp_path, monkeypatch):
    client, _ = api(tmp_path)
    stopped = threading.Event()
    client.app.state.update_shutdown = stopped.set
    monkeypatch.setattr(api_module, "_desktop_shutdown_supported", lambda _app: True)
    monkeypatch.setenv("DESKTOP_CONTROL_TOKEN", "test-desktop-token")

    current = client.get("/auth/me").json()
    assert current["desktop_app"] is True
    assert current["desktop_control_token"] == "test-desktop-token"
    assert client.post("/api/v1/admin/shutdown").status_code == 403
    response = client.post(
        "/api/v1/admin/shutdown",
        headers={"X-Desktop-Control-Token": "test-desktop-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}
    assert stopped.wait(1)

    monkeypatch.setattr(api_module, "_desktop_shutdown_supported", lambda _app: False)
    assert client.post(
        "/api/v1/admin/shutdown",
        headers={"X-Desktop-Control-Token": "test-desktop-token"},
    ).status_code == 409


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
    assert monthly["count"] == 0


def test_monthly_kpi_uses_account_targets_and_clear_subset_total(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), daily_target_commission=100))

    monthly = client.get("/api/v1/monthly-kpi", params={"account": "CHIISTORE", "month": "2026-03"}).json()
    by_account = {item["account"]: item for item in monthly["items"]}
    filtered = client.get(
        "/api/v1/monthly-kpi",
        params={"account": "CHIISTORE", "month": "2026-03", "status": "settled"},
    ).json()

    assert by_account["CHIISTORE"]["daily_target"] == 100
    assert by_account["ALL"]["daily_target"] == 100
    assert by_account["ALL"]["monthly_target"] == 3100
    assert all(item["daily_target"] is None for item in filtered["items"])


def test_monthly_kpi_spanning_two_months_sums_targets_instead_of_reporting_one(tmp_path):
    """Bộ lọc "30 ngày qua" hay bắc qua ranh giới tháng, mà KPI đặt riêng cho từng tháng.

    Trước đây phạm vi này trả về hai dòng cho cùng một tài khoản; giao diện chỉ đọc được một
    dòng nên tiến độ mục tiêu đo một khoảng khác hẳn hoa hồng hiển thị ngay cạnh nó.
    """
    client, engine = api(tmp_path)
    rows = [
        normalized(**{"ID đơn hàng": f"O{index}", "Ngày đặt hàng": f"{day} 10:00:00"})
        for index, day in enumerate(["20/07/2026", "25/07/2026", "05/08/2026"])
    ]
    import_rows(engine, filename="two-months.xlsx", file_bytes=b"two", account="CHIISTORE", rows=rows)
    with engine.begin() as conn:
        for month in (date(2026, 7, 1), date(2026, 8, 1)):
            conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=month, daily_target_commission=1000))

    scope = {"account": "CHIISTORE", "start": "2026-07-13", "end": "2026-08-11"}
    items = client.get("/api/v1/monthly-kpi", params=scope).json()["items"]
    overview = client.get("/api/v1/overview", params=scope).json()["items"]

    kpi = [item for item in items if item["account"] == "CHIISTORE"]
    total = next(item for item in overview if item["account"] == "ALL")
    assert len(kpi) == 1, "mỗi tài khoản chỉ được một dòng cho cả phạm vi"
    # 19 ngày của tháng 7 (13-31) cộng 11 ngày của tháng 8 (1-11).
    assert kpi[0]["days_in_scope"] == 30
    assert kpi[0]["monthly_target"] == 30_000
    # Tiến độ phải đo đúng khoảng mà hoa hồng trên cùng màn hình đang đo.
    assert kpi[0]["actual_commission"] == total["actual_commission"]


def test_monthly_kpi_without_target_for_every_month_in_scope_reports_no_target(tmp_path):
    """Thiếu KPI một tháng thì tổng mục tiêu là chưa xác định, không phải tổng mấy tháng có đặt."""
    client, engine = api(tmp_path)
    rows = [
        normalized(**{"ID đơn hàng": f"O{index}", "Ngày đặt hàng": f"{day} 10:00:00"})
        for index, day in enumerate(["20/07/2026", "05/08/2026"])
    ]
    import_rows(engine, filename="gap.xlsx", file_bytes=b"gap", account="CHIISTORE", rows=rows)
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 8, 1), daily_target_commission=1000))

    items = client.get(
        "/api/v1/monthly-kpi",
        params={"account": "CHIISTORE", "start": "2026-07-13", "end": "2026-08-11"},
    ).json()["items"]

    kpi = next(item for item in items if item["account"] == "CHIISTORE")
    assert kpi["monthly_target"] is None
    assert kpi["target_achievement"] is None


def test_copy_previous_targets_fills_only_missing_accounts(tmp_path):
    """Chép KPI sang tháng mới, nhưng không đè lên tài khoản đã đặt cho tháng đó."""
    client, engine = api(tmp_path)
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), daily_target_commission=100))
        conn.execute(monthly_targets.insert().values(account="EMLINHNOIY", month=date(2026, 3, 1), daily_target_commission=200))
        # THAOBRA đã có KPI riêng cho tháng 4 — chép không được phép ghi đè con số này.
        conn.execute(monthly_targets.insert().values(account="THAOBRA", month=date(2026, 3, 1), daily_target_commission=300))
        conn.execute(monthly_targets.insert().values(account="THAOBRA", month=date(2026, 4, 1), daily_target_commission=999))

    payload = client.post("/api/v1/targets/2026-04/copy-previous").json()
    after = {item["account"]: item["daily_target_commission"] for item in client.get("/api/v1/targets", params={"month": "2026-04"}).json()["items"]}

    assert payload["from_month"] == "2026-03"
    assert [item["account"] for item in payload["copied"]] == ["CHIISTORE", "EMLINHNOIY"]
    assert payload["kept"] == ["THAOBRA"]
    assert after == {"CHIISTORE": 100, "EMLINHNOIY": 200, "THAOBRA": 999}

    # Bấm lần nữa không được nhân đôi hay đổi gì.
    repeat = client.post("/api/v1/targets/2026-04/copy-previous").json()
    assert repeat["copied"] == []
    assert {item["account"]: item["daily_target_commission"] for item in client.get("/api/v1/targets", params={"month": "2026-04"}).json()["items"]} == after


def test_copy_previous_targets_crosses_the_year_boundary(tmp_path):
    """Tháng 1 phải lùi về tháng 12 năm trước, không phải tháng 0 cùng năm."""
    client, engine = api(tmp_path)
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2025, 12, 1), daily_target_commission=750))

    payload = client.post("/api/v1/targets/2026-01/copy-previous").json()

    assert payload["from_month"] == "2025-12"
    assert payload["copied"] == [{"account": "CHIISTORE", "daily_target_commission": 750}]


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


def test_orders_sort_is_applied_in_sql_and_rejects_unknown_columns(tmp_path):
    client, engine = api(tmp_path)
    import_rows(
        engine,
        filename="sortable.xlsx",
        file_bytes=b"sortable",
        account="CHIISTORE",
        rows=[
            normalized(**{"ID đơn hàng": "O1", "ID SKU": "S1", "GMV": "300.000"}),
            normalized(**{"ID đơn hàng": "O2", "ID SKU": "S2", "GMV": "100.000"}),
            normalized(**{"ID đơn hàng": "O3", "ID SKU": "S3", "GMV": "200.000"}),
        ],
    )

    ascending = client.get("/api/v1/orders", params={"sort": "gmv", "direction": "asc"}).json()
    descending = client.get("/api/v1/orders", params={"sort": "gmv", "direction": "desc"}).json()
    first_page = client.get("/api/v1/orders", params={"sort": "gmv", "direction": "asc", "limit": 2}).json()

    assert [row["gmv"] for row in ascending["items"]] == [100000, 200000, 300000]
    assert [row["gmv"] for row in descending["items"]] == [300000, 200000, 100000]
    assert [row["gmv"] for row in first_page["items"]] == [100000, 200000]
    assert client.get("/api/v1/orders", params={"sort": "raw_json"}).status_code == 422


def test_undo_import_endpoint_previews_then_removes_the_batch(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    second = import_rows(
        engine,
        filename="b.xlsx",
        file_bytes=b"b",
        account="CHIISTORE",
        rows=[normalized(**{"GMV": "900.000"}), normalized(**{"ID đơn hàng": "O9", "ID SKU": "S9"})],
    )
    batch_id = second["batch_id"]

    preview = client.get(f"/api/v1/imports/{batch_id}/undo-preview").json()
    assert preview["confirmation"] == f"HOAN TAC {batch_id}"
    assert (preview["removed_lines"], preview["restored_lines"]) == (1, 1)

    assert client.request("DELETE", f"/api/v1/imports/{batch_id}", json={"confirmation": "sai"}).status_code == 422

    removed = client.request("DELETE", f"/api/v1/imports/{batch_id}", json={"confirmation": preview["confirmation"]})
    assert removed.status_code == 200
    assert removed.json()["removed_versions"] == 2

    assert client.get(f"/api/v1/imports/{batch_id}/undo-preview").status_code == 404
    assert client.get("/api/v1/orders").json()["total"] == 1
    assert client.get("/api/v1/imports").json()["count"] == 1


def test_order_versions_endpoint_lists_history_newest_first(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    import_rows(engine, filename="b.xlsx", file_bytes=b"b", account="CHIISTORE", rows=[normalized(**{"GMV": "900.000"})])

    business_key = client.get("/api/v1/orders").json()["items"][0]["business_key"]
    payload = client.get(f"/api/v1/orders/{quote(business_key, safe='')}/versions").json()

    assert payload["count"] == 2
    assert [item["version"] for item in payload["items"]] == [2, 1]
    assert [item["filename"] for item in payload["items"]] == ["b.xlsx", "a.xlsx"]
    assert client.get("/api/v1/orders/KHONG|CO|GI/versions").status_code == 404


def test_import_requires_account_and_imports_xlsx(tmp_path):
    client, _ = api(tmp_path)
    data = xlsx_bytes([raw_export_row()])

    missing = client.post("/api/v1/imports", files={"file": ("affiliate_orders.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    virtual = client.post(
        "/api/v1/imports",
        data={"account": "ALL"},
        files={"file": ("affiliate_orders.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    unknown = client.post(
        "/api/v1/imports",
        data={"account": "NOT_ALLOWED"},
        files={"file": ("affiliate_orders.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    wrong_type = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("orders.csv", data, "text/csv")},
    )
    wrong_name = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("orders.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    created = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("affiliate_orders_7674048855708600085.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    duplicate = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("affiliate_orders-copy.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert missing.status_code == 422
    assert virtual.status_code == 422
    assert unknown.status_code == 403
    assert wrong_type.status_code == 415
    assert wrong_name.status_code == 415
    assert wrong_name.json()["detail"] == FILENAME_REJECT_MESSAGE
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
        files={"file": ("affiliate_orders.xlsx", b"x", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "File exceeds 0 MB"}


def test_owner_reset_data_creates_backup_deletes_imports_and_preserves_targets(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), daily_target_commission=100))

    wrong = client.post("/api/v1/admin/reset-data", json={"confirmation": "RESET DATA"})
    response = client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"})

    assert wrong.status_code == 422
    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_counts"]["import_batches"] == 1
    assert payload["deleted_counts"]["order_line_versions"] == 1
    assert payload["backup_path"].endswith(".db")
    with engine.connect() as conn:
        assert conn.execute(select(import_batches)).all() == []
        assert conn.execute(select(order_line_versions)).all() == []
        assert conn.execute(select(monthly_targets.c.account, monthly_targets.c.daily_target_commission)).all() == [("CHIISTORE", 100)]
        assert conn.execute(select(accounts.c.code).where(accounts.c.code == "CHIISTORE")).scalar_one() == "CHIISTORE"


def test_reset_data_shrinks_the_database_file_instead_of_leaving_dead_pages(tmp_path):
    client, engine = api(tmp_path)
    import_rows(
        engine,
        filename="big.xlsx",
        file_bytes=b"big",
        account="CHIISTORE",
        rows=[normalized(**{"ID đơn hàng": f"O{index}", "ID SKU": f"S{index}"}) for index in range(2000)],
    )
    db_path = tmp_path / "api.db"
    engine.dispose()
    before = db_path.stat().st_size

    payload = client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"}).json()

    after = db_path.stat().st_size
    # Không VACUUM thì xoá xong file vẫn nằm ì nguyên kích thước cũ.
    assert before > 1_000_000
    assert after < before / 2
    assert payload["freed_bytes"] >= before - after
    assert client.get("/api/v1/orders").json()["total"] == 0


def test_backups_keep_only_the_most_recent_few_instead_of_piling_up(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    backup_dir = tmp_path / "backups"

    for _ in range(6):
        assert client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"}).status_code == 200

    kept = sorted(backup_dir.glob("*.db"))
    assert len(kept) == reset_data_module.BACKUP_RETENTION
    assert client.get("/api/v1/admin/backups").json()["count"] == reset_data_module.BACKUP_RETENTION


def test_restore_never_prunes_the_backup_it_is_restoring(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    # Lấp đủ hạn mức rồi khôi phục từ bản CŨ NHẤT còn giữ. Bản sao lưu an toàn tạo trong lúc
    # khôi phục sẽ dọn bớt, và nếu không chừa thì nó xoá đúng bản đang được đọc.
    for _ in range(reset_data_module.BACKUP_RETENTION):
        assert client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"}).status_code == 200
    oldest = client.get("/api/v1/admin/backups").json()["items"][-1]["id"]

    restored = client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": oldest, "confirmation": "KHOI PHUC DU LIEU"},
    )
    assert restored.status_code == 200
    assert (tmp_path / "backups" / oldest).exists()


def test_reset_data_aborts_before_delete_when_backup_check_fails(tmp_path, monkeypatch):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])

    def fail_backup_check(_backup_path):
        raise RuntimeError("bad backup")

    monkeypatch.setattr(reset_data_module, "_check_backup", fail_backup_check)

    response = client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"})

    assert response.status_code == 500
    with engine.connect() as conn:
        assert conn.execute(select(import_batches)).all()
        assert conn.execute(select(order_line_versions)).all()


def test_reset_data_does_not_lose_concurrent_import_after_backup(tmp_path, monkeypatch):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    concurrent_row = normalized(**{"ID đơn hàng": "O2", "ID SKU": "S2"})
    backup_checked = threading.Event()
    import_started = threading.Event()
    original_check_backup = reset_data_module._check_backup

    def slow_backup_check(backup_path):
        original_check_backup(backup_path)
        backup_checked.set()
        import_started.wait(2)
        time.sleep(0.2)

    monkeypatch.setattr(reset_data_module, "_check_backup", slow_backup_check)
    reset_result = {}
    import_result = {}

    def reset():
        reset_result["response"] = client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"})

    def concurrent_import():
        import_started.set()
        import_result["summary"] = import_rows(
            engine,
            filename="concurrent.xlsx",
            file_bytes=b"concurrent",
            account="CHIISTORE",
            rows=[concurrent_row],
        )

    reset_thread = threading.Thread(target=reset)
    reset_thread.start()
    assert backup_checked.wait(2)
    import_thread = threading.Thread(target=concurrent_import)
    import_thread.start()
    reset_thread.join(2)
    import_thread.join(2)

    assert not reset_thread.is_alive()
    assert not import_thread.is_alive()
    assert reset_result["response"].status_code == 200
    assert import_result["summary"]["inserted"] == 1
    business_key = concurrent_row["business_key"]
    with engine.connect() as conn:
        in_live_db = bool(
            conn.execute(
                select(order_line_versions.c.id).where(order_line_versions.c.business_key == business_key)
            ).first()
        )
    backup_path = reset_result["response"].json()["backup_path"]
    with sqlite3.connect(backup_path) as conn:
        in_backup = bool(
            conn.execute(
                "SELECT 1 FROM order_line_versions WHERE business_key = ?",
                (business_key,),
            ).fetchone()
        )
    assert in_live_db or in_backup


def test_optional_static_web_mount_keeps_api_routes(tmp_path, monkeypatch):
    static_dir = tmp_path / "web"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>Ops Cockpit</h1>", encoding="utf-8")
    (static_dir / "sw.js").write_text(
        'const CACHE = "tiktok-affiliate-report-shell-__APP_VERSION__";',
        encoding="utf-8",
    )
    monkeypatch.setenv("WEB_STATIC_DIR", str(static_dir))
    client, _ = api(tmp_path)

    assert client.get("/health").json() == {"status": "ok", "app_version": APP_VERSION}
    index = client.get("/")
    assert "Ops Cockpit" in index.text
    # Không có header này, WebView/trình duyệt có thể tự phục vụ bản HTML cũ sau khi app đã
    # update xong mà không hỏi lại server — đúng triệu chứng "update xong vẫn thấy UI cũ".
    assert index.headers["cache-control"] == "no-cache"
    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert "__APP_VERSION__" not in service_worker.text
    assert f"tiktok-affiliate-report-shell-{APP_VERSION}" in service_worker.text
    assert service_worker.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_static_export_mount_resolves_flattened_rsc_payloads_without_open_rewrites(tmp_path, monkeypatch):
    static_dir = tmp_path / "web"
    analytics = static_dir / "analytics"
    settings = static_dir / "settings" / "update"
    (analytics / "__next.analytics").mkdir(parents=True)
    (settings / "__next.settings" / "update").mkdir(parents=True)
    (static_dir / "index.html").write_text("<h1>Ops Cockpit</h1>", encoding="utf-8")
    (analytics / "__next.analytics" / "__PAGE__.txt").write_text("analytics-page", encoding="utf-8")
    (settings / "__next.settings" / "update.txt").write_text("settings-update", encoding="utf-8")
    (settings / "__next.settings" / "update" / "__PAGE__.txt").write_text("settings-update-page", encoding="utf-8")
    monkeypatch.setenv("WEB_STATIC_DIR", str(static_dir))
    client, _ = api(tmp_path)

    assert client.get("/analytics/__next.analytics.__PAGE__.txt").text == "analytics-page"
    assert client.get("/settings/update/__next.settings.update.txt").text == "settings-update"
    assert client.get("/settings/update/__next.settings.update.__PAGE__.txt").text == "settings-update-page"
    assert client.get("/analytics/__next.analytics.missing.txt").status_code == 404
    assert client.get("/analytics/__next.analytics...secret.txt").status_code == 404


def test_owner_account_crud_hard_delete_with_backup_and_restore(tmp_path):
    client, engine = api(tmp_path)
    created = client.post(
        "/api/v1/accounts",
        json={"code": "new_acc", "display_name": "New Account"},
    )
    assert created.status_code == 201
    assert created.json()["code"] == "NEW_ACC"

    updated = client.patch(
        "/api/v1/accounts/NEW_ACC",
        json={"display_name": "New Account 2", "display_order": 5},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "New Account 2"

    import_rows(engine, filename="new.xlsx", file_bytes=b"new", account="NEW_ACC", rows=[normalized(account="NEW_ACC")])
    preview = client.get("/api/v1/accounts/NEW_ACC/delete-preview")
    assert preview.status_code == 200
    assert preview.json()["dependency_counts"]["order_line_versions"] == 1
    assert preview.json()["action"] == "hard_delete"

    wrong = client.request("DELETE", "/api/v1/accounts/NEW_ACC", json={"confirmation": "XOA"})
    deleted = client.request("DELETE", "/api/v1/accounts/NEW_ACC", json={"confirmation": "XOA NEW_ACC"})
    assert wrong.status_code == 422
    assert deleted.status_code == 200
    assert deleted.json()["hard_deleted"] is True
    assert deleted.json()["backup_path"].endswith(".db")
    assert all(item["code"] != "NEW_ACC" for item in client.get("/api/v1/accounts").json()["items"])
    assert client.get("/api/v1/overview", params={"account": "NEW_ACC"}).status_code == 403

    backup_name = deleted.json()["backup_path"].replace("\\", "/").split("/")[-1]
    restored = client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": backup_name, "confirmation": "KHOI PHUC DU LIEU"},
    )
    assert restored.status_code == 200
    assert any(item["code"] == "NEW_ACC" for item in client.get("/api/v1/accounts").json()["items"])


def test_create_account_with_space_in_code_returns_pydantic_array_detail(tmp_path):
    # Pydantic tự chặn request TRƯỚC KHI create_account_endpoint chạy, nên response mang hình
    # dạng detail khác hẳn — MẢNG {msg, loc, ...} thay vì chuỗi. web/src/lib/api.ts phải giải mã
    # được hình dạng này; test ở tầng Python thuần (test_accounts.py) không đi qua Pydantic nên
    # không tự phát hiện được lớp lỗi này.
    client, _ = api(tmp_path)
    response = client.post("/api/v1/accounts", json={"code": "bad code", "display_name": "X"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_create_account_accepts_period_in_code(tmp_path):
    client, _ = api(tmp_path)
    response = client.post("/api/v1/accounts", json={"code": "sarah.reign", "display_name": "Sarah"})
    assert response.status_code == 201
    assert response.json()["code"] == "SARAH.REIGN"


def test_analytics_and_excel_exports_follow_account_scope(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])

    payload = client.get(
        "/api/v1/analytics",
        params={"account": "CHIISTORE", "start": "2026-03-01", "end": "2026-03-31"},
    )
    all_scope = client.get(
        "/api/v1/analytics",
        params={"account": "ALL", "start": "2026-03-01", "end": "2026-03-31"},
    )
    mixed_all_scope = client.get(
        "/api/v1/analytics",
        params=[("account", "ALL"), ("account", "NOT_ALLOWED")],
    )
    orders_export = client.get("/api/v1/orders/export.xlsx", params={"account": "CHIISTORE"})
    daily_export = client.get(
        "/api/v1/reports/daily.xlsx",
        params={"account": "CHIISTORE", "start": "2026-03-01", "end": "2026-03-31"},
    )

    assert payload.status_code == 200
    assert all_scope.status_code == 200
    assert mixed_all_scope.status_code == 422
    assert all_scope.json()["summary"] == payload.json()["summary"]
    assert payload.json()["summary"]["orders"] == 1
    assert payload.json()["products"][0]["label"] == "Sản phẩm"
    assert orders_export.status_code == 200 and orders_export.content.startswith(b"PK")
    assert daily_export.status_code == 200 and daily_export.content.startswith(b"PK")


def test_bang_noi_dung_nhan_dien_tung_dong_thay_vi_lap_lai_loai_noi_dung(tmp_path):
    """Nội dung không có tên riêng, chỉ có content_type — và mọi dòng đều là "Video".

    Đo trên dữ liệu thật: 343 content_id khác nhau nhưng đúng một content_type, nên nhãn lấy
    theo content_type làm cả bảng xếp hạng thành 20 dòng giống hệt nhau. Trả label về
    content_type thì test này ĐỎ.
    """
    client, engine = api(tmp_path)
    rows = [
        normalized(**{"ID đơn hàng": "O1", "ID SKU": "S1", "Id nội dung": "C-AAA", "Loại nội dung": "Video"}),
        normalized(**{"ID đơn hàng": "O2", "ID SKU": "S2", "Id nội dung": "C-BBB", "Loại nội dung": "Video"}),
    ]
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=rows)

    content = client.get("/api/v1/analytics").json()["content"]

    nhan = [row["label"] for row in content]
    assert len(set(nhan)) == len(nhan), f"nhãn trùng nhau, không phân biệt được dòng nào: {nhan}"
    assert set(nhan) == {"C-AAA", "C-BBB"}
