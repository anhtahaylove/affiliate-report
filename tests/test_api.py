from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date
from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import select

import tiktok_affiliate_report.api as api_module
import tiktok_affiliate_report.reset_data as reset_data_module
from tiktok_affiliate_report.accounts import create_account
from tiktok_affiliate_report.api import create_app
from tiktok_affiliate_report.db import (
    accounts,
    get_engine,
    import_batches,
    import_rows,
    monthly_targets,
    order_line_versions,
)
from tiktok_affiliate_report.parser import EXPECTED_HEADERS, normalize_row
from tiktok_affiliate_report.version import APP_VERSION


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
    assert client.get("/health").json() == {"status": "ok"}
    meta = client.get("/api/v1/meta").json()

    assert meta["accounts"] == ["CHIISTORE", "EMLINHNOIY", "THAOBRA"]
    assert [item["code"] for item in meta["account_items"]] == meta["accounts"]
    assert meta["statuses"] == ["settled", "ineligible", "pending", "unknown"]
    assert meta["max_upload_mb"] == 20


def test_fresh_database_has_no_user_specific_accounts_or_targets(tmp_path):
    engine = get_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    client = TestClient(create_app(engine), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

    assert client.get("/api/v1/meta").json()["accounts"] == []
    assert client.get("/api/v1/targets").json()["items"] == []


def test_local_owner_can_check_and_schedule_verified_update(tmp_path, monkeypatch):
    client, _ = api(tmp_path)
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"verified")
    scheduled = {}

    monkeypatch.setattr(
        api_module,
        "check_for_update",
        lambda: {
            "current_version": APP_VERSION,
            "latest_version": "1.2.1",
            "available": True,
            "installable": True,
        },
    )
    monkeypatch.setattr(api_module, "_automatic_update_supported", lambda _app: True)
    monkeypatch.setattr(
        api_module,
        "download_latest_update",
        lambda _data_dir: {
            "version": "1.2.1",
            "installer_path": str(installer),
            "sha256": "A" * 64,
            "release_url": "https://github.com/example/release",
        },
    )

    def capture_schedule(path, sha256, log_path, shutdown):
        scheduled.update(path=path, sha256=sha256, log_path=log_path, shutdown=shutdown)

    monkeypatch.setattr(api_module, "schedule_installer", capture_schedule)
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
        "status": "scheduled",
        "version": "1.2.1",
        "sha256": "A" * 64,
        "release_url": "https://github.com/example/release",
    }
    assert scheduled["path"] == installer
    assert scheduled["sha256"] == "A" * 64
    assert scheduled["log_path"].name == "updater.log"
    assert duplicate.status_code == 409


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
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), target_commission=100))

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
    virtual = client.post(
        "/api/v1/imports",
        data={"account": "ALL"},
        files={"file": ("orders.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
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
    assert virtual.status_code == 422
    assert unknown.status_code == 403
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


def test_owner_reset_data_creates_backup_deletes_imports_and_preserves_targets(tmp_path):
    client, engine = api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), target_commission=100))

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
        assert conn.execute(select(monthly_targets.c.account, monthly_targets.c.target_commission)).all() == [("CHIISTORE", 100)]
        assert conn.execute(select(accounts.c.code).where(accounts.c.code == "CHIISTORE")).scalar_one() == "CHIISTORE"


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
    monkeypatch.setenv("WEB_STATIC_DIR", str(static_dir))
    client, _ = api(tmp_path)

    assert client.get("/health").json() == {"status": "ok"}
    assert "Ops Cockpit" in client.get("/").text


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
