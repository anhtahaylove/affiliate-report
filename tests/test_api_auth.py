from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from tests.test_api import normalized, raw_export_row, xlsx_bytes
from tiktok_affiliate_report.accounts import create_account
from tiktok_affiliate_report.api import create_app
from tiktok_affiliate_report.auth import AuthService, AuthSettings
import tiktok_affiliate_report.reset_data as reset_data_module
from tiktok_affiliate_report.db import (
    app_users,
    auth_sessions,
    get_engine,
    import_batches,
    import_rows,
    monthly_targets,
    order_line_versions,
    raw_import_rows,
)


def oidc_api(tmp_path):
    engine = get_engine(f"sqlite:///{(tmp_path / 'api-auth.db').as_posix()}")
    settings = AuthSettings(
        mode="oidc",
        cookie_secure=False,
        oidc_issuer="https://idp.example.test",
        oidc_client_id="client",
        oidc_redirect_uri="http://api.example.test/auth/callback",
        bootstrap_owner_email="owner@example.test",
        allowed_emails=("owner@example.test", "viewer@example.test"),
    )
    auth = AuthService(engine, settings)
    app = create_app(engine, auth)
    for code in ("CHIISTORE", "EMLINHNOIY", "THAOBRA"):
        create_account(engine, code, display_name=code)
    return TestClient(app), engine, auth


def login(client: TestClient, auth: AuthService, email: str, subject: str):
    principal = auth.provision_user(
        issuer=auth.settings.oidc_issuer or "",
        subject=subject,
        email=email,
    )
    tokens = auth.create_session(principal)
    client.cookies.set(auth.settings.cookie_name, tokens.session_token)
    client.cookies.set(auth.settings.csrf_cookie_name, tokens.csrf_token)
    return principal, tokens


def test_oidc_mode_requires_session_but_health_stays_public(tmp_path):
    client, _, _ = oidc_api(tmp_path)

    assert client.get("/health").status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert client.get("/api/v1/meta").status_code == 401
    assert client.get("/api/v1/overview").status_code == 401
    assert client.get("/auth/callback", params={"code": "x", "state": "x"}).status_code == 400


def test_local_mode_rejects_non_loopback_requests_even_if_asgi_is_exposed(tmp_path):
    engine = get_engine(f"sqlite:///{(tmp_path / 'local-public.db').as_posix()}")
    client = TestClient(
        create_app(engine, AuthService(engine, AuthSettings(mode="local"))),
        base_url="http://report.example.test",
        client=("192.0.2.10", 50000),
    )

    assert client.get("/health").status_code == 200
    assert client.get("/auth/me").status_code == 403
    assert client.get("/api/v1/meta").status_code == 403


def test_viewer_only_sees_assigned_accounts_and_cannot_import(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    import_rows(engine, filename="b.xlsx", file_bytes=b"b", account="EMLINHNOIY", rows=[normalized("EMLINHNOIY")])
    viewer, tokens = login(client, auth, "viewer@example.test", "viewer")
    auth.update_user(viewer.user_id or 0, accounts=["CHIISTORE"])

    assert client.get("/api/v1/meta").json()["accounts"] == ["CHIISTORE"]
    assert client.get("/api/v1/accounts").status_code == 403
    assert client.post(
        "/api/v1/accounts",
        json={"code": "NEW", "display_name": "New"},
        headers={"X-CSRF-Token": tokens.csrf_token},
    ).status_code == 403
    overview = client.get("/api/v1/overview").json()
    assert {row["account"] for row in overview["items"]} == {"CHIISTORE", "ALL"}
    assert client.get("/api/v1/overview", params={"account": "EMLINHNOIY"}).status_code == 403
    denied = client.post(
        "/api/v1/imports",
        data={"account": "CHIISTORE"},
        files={"file": ("orders.xlsx", xlsx_bytes([raw_export_row()]))},
        headers={"X-CSRF-Token": tokens.csrf_token},
    )
    assert denied.status_code == 403


def test_undo_import_is_role_and_account_scoped(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    mine = import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    other = import_rows(engine, filename="b.xlsx", file_bytes=b"b", account="EMLINHNOIY", rows=[normalized("EMLINHNOIY")])
    viewer, tokens = login(client, auth, "viewer@example.test", "viewer")
    auth.update_user(viewer.user_id or 0, accounts=["CHIISTORE"])

    assert client.get(f"/api/v1/imports/{mine['batch_id']}/undo-preview").status_code == 403

    auth.update_user(viewer.user_id or 0, role="operator", accounts=["CHIISTORE"])

    assert client.get(f"/api/v1/imports/{mine['batch_id']}/undo-preview").status_code == 200
    assert client.get(f"/api/v1/imports/{other['batch_id']}/undo-preview").status_code == 403
    assert client.request(
        "DELETE",
        f"/api/v1/imports/{other['batch_id']}",
        json={"confirmation": f"HOAN TAC {other['batch_id']}"},
        headers={"X-CSRF-Token": tokens.csrf_token},
    ).status_code == 403
    assert client.request(
        "DELETE",
        f"/api/v1/imports/{mine['batch_id']}",
        json={"confirmation": f"HOAN TAC {mine['batch_id']}"},
    ).status_code == 403  # thiếu CSRF token
    assert client.request(
        "DELETE",
        f"/api/v1/imports/{mine['batch_id']}",
        json={"confirmation": f"HOAN TAC {mine['batch_id']}"},
        headers={"X-CSRF-Token": tokens.csrf_token},
    ).status_code == 200


def test_import_history_is_account_scoped_and_secret_safe(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    import_rows(engine, filename="b.xlsx", file_bytes=b"b", account="EMLINHNOIY", rows=[normalized("EMLINHNOIY")])
    viewer, _ = login(client, auth, "viewer@example.test", "viewer")
    auth.update_user(viewer.user_id or 0, accounts=["CHIISTORE"])

    visible = client.get("/api/v1/imports").json()
    denied = client.get("/api/v1/imports", params={"account": "EMLINHNOIY"})
    item = visible["items"][0]

    assert visible["count"] == 1
    assert item["filename"] == "a.xlsx"
    assert item["account"] == "CHIISTORE"
    assert {"file_sha", "auth_subject"} & set(item) == set()
    assert denied.status_code == 403


def test_operator_requires_csrf_and_cannot_upload_another_account(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    operator, tokens = login(client, auth, "viewer@example.test", "operator")
    auth.update_user(operator.user_id or 0, role="operator", accounts=["CHIISTORE"])
    upload = {
        "data": {"account": "CHIISTORE"},
        "files": {"file": ("orders.xlsx", xlsx_bytes([raw_export_row()]))},
    }

    assert client.post("/api/v1/imports", **upload).status_code == 403
    cross_account = client.post(
        "/api/v1/imports",
        data={"account": "THAOBRA"},
        files=upload["files"],
        headers={"X-CSRF-Token": tokens.csrf_token},
    )
    assert cross_account.status_code == 403
    allowed = client.post(
        "/api/v1/imports",
        **upload,
        headers={"X-CSRF-Token": tokens.csrf_token},
    )
    assert allowed.status_code == 200
    assert allowed.json()["inserted"] == 1
    with engine.connect() as conn:
        audit = conn.execute(select(import_batches)).mappings().one()
    assert audit["auth_method"] == "oidc"
    assert audit["auth_subject"] == "https://idp.example.test:operator"
    assert audit["uploaded_by_label"] == "viewer@example.test"


def test_targets_are_editable_by_role_and_account_scope(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    operator, tokens = login(client, auth, "viewer@example.test", "operator")
    auth.update_user(operator.user_id or 0, role="operator", accounts=["CHIISTORE"])

    missing_csrf = client.put("/api/v1/targets/CHIISTORE/2026-03", json={"target_commission": 111})
    updated = client.put(
        "/api/v1/targets/CHIISTORE/2026-03",
        json={"target_commission": 111},
        headers={"X-CSRF-Token": tokens.csrf_token},
    )
    denied_account = client.put(
        "/api/v1/targets/THAOBRA/2026-03",
        json={"target_commission": 222},
        headers={"X-CSRF-Token": tokens.csrf_token},
    )
    denied_all = client.put(
        "/api/v1/targets/ALL/2026-03",
        json={"target_commission": 333},
        headers={"X-CSRF-Token": tokens.csrf_token},
    )

    assert missing_csrf.status_code == 403
    assert updated.status_code == 200
    assert updated.json() == {"account": "CHIISTORE", "month": "2026-03", "target_commission": 111}
    assert denied_account.status_code == 403
    assert denied_all.status_code == 403
    visible = client.get("/api/v1/targets", params={"month": "2026-03"}).json()["items"]
    assert visible == [{"account": "CHIISTORE", "month": "2026-03", "target_commission": 111}]

    with engine.connect() as conn:
        target = conn.execute(
            select(monthly_targets.c.target_commission).where(monthly_targets.c.account == "CHIISTORE")
        ).scalar_one()
    assert target == 111


def test_owner_can_edit_all_target_and_validation_rejects_bad_values(tmp_path):
    client, _, auth = oidc_api(tmp_path)
    _, tokens = login(client, auth, "owner@example.test", "owner")
    headers = {"X-CSRF-Token": tokens.csrf_token}

    assert client.put("/api/v1/targets/ALL/not-a-month", json={"target_commission": 1}, headers=headers).status_code == 422
    assert client.put("/api/v1/targets/ALL/2026-03", json={"target_commission": -1}, headers=headers).status_code == 422
    assert client.put(
        "/api/v1/targets/ALL/2026-03",
        json={"target_commission": 1_000_000_000_001},
        headers=headers,
    ).status_code == 422
    updated = client.put("/api/v1/targets/ALL/2026-03", json={"target_commission": 999}, headers=headers)
    replaced = client.put("/api/v1/targets/ALL/2026-03", json={"target_commission": 1000}, headers=headers)

    assert updated.status_code == 200
    assert replaced.status_code == 200
    targets = client.get("/api/v1/targets", params={"account": "ALL", "month": "2026-03"}).json()["items"]
    assert targets == [{"account": "ALL", "month": "2026-03", "target_commission": 1000}]


def test_owner_can_manage_users_but_cannot_remove_own_owner_access(tmp_path):
    client, _, auth = oidc_api(tmp_path)
    owner, tokens = login(client, auth, "owner@example.test", "owner")
    viewer = auth.provision_user(
        issuer=auth.settings.oidc_issuer or "",
        subject="viewer",
        email="viewer@example.test",
    )
    headers = {"X-CSRF-Token": tokens.csrf_token}

    users = client.get("/api/v1/admin/users")
    assert users.status_code == 200
    assert users.json()["count"] == 2
    updated = client.patch(
        f"/api/v1/admin/users/{viewer.user_id}",
        json={"role": "operator", "accounts": ["THAOBRA"], "active": True},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "operator"
    assert updated.json()["active"] is True
    assert updated.json()["accounts"] == ["THAOBRA"]
    self_demotion = client.patch(
        f"/api/v1/admin/users/{owner.user_id}",
        json={"role": "viewer"},
        headers=headers,
    )
    assert self_demotion.status_code == 409


def test_credentialed_cors_rejects_wildcard(tmp_path, monkeypatch):
    engine = get_engine(f"sqlite:///{(tmp_path / 'cors.db').as_posix()}")
    monkeypatch.setenv("API_CORS_ORIGINS", "*")

    try:
        create_app(engine)
    except ValueError as exc:
        assert "không được dùng *" in str(exc)
    else:
        raise AssertionError("Wildcard credentialed CORS must be rejected")


def _count(conn, table):
    return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_owner_reset_data_requires_csrf_confirmation_and_preserves_auth(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), target_commission=123))
    owner, tokens = login(client, auth, "owner@example.test", "owner")
    headers = {"X-CSRF-Token": tokens.csrf_token}

    assert client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"}).status_code == 403
    assert client.post("/api/v1/admin/reset-data", json={"confirmation": "nope"}, headers=headers).status_code == 422

    response = client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"}, headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_counts"] == {
        "raw_import_rows": 1,
        "order_line_versions": 1,
        "import_batches": 1,
    }
    assert payload["targets_preserved"] is True
    backup_path = Path(payload["backup_path"])
    assert backup_path.exists()
    assert backup_path.parent.name == "backups"
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert backup.execute("select count(*) from import_batches").fetchone() == (1,)
        assert backup.execute("select count(*) from app_users").fetchone() == (1,)

    with engine.connect() as conn:
        assert _count(conn, raw_import_rows) == 0
        assert _count(conn, order_line_versions) == 0
        assert _count(conn, import_batches) == 0
        assert _count(conn, monthly_targets) == 1
        assert _count(conn, app_users) == 1
        assert _count(conn, auth_sessions) == 1
    assert client.get("/auth/me").json()["email"] == owner.email


def test_reset_data_is_owner_only_and_rejects_shared_sqlite(tmp_path):
    client, _, auth = oidc_api(tmp_path)
    viewer, tokens = login(client, auth, "viewer@example.test", "viewer")
    auth.update_user(viewer.user_id or 0, role="operator", accounts=["CHIISTORE"])

    denied = client.post(
        "/api/v1/admin/reset-data",
        json={"confirmation": "XOA DU LIEU"},
        headers={"X-CSRF-Token": tokens.csrf_token},
    )

    assert denied.status_code == 403

    engine = get_engine(f"sqlite:///{(tmp_path / 'safe.db').as_posix()}")
    shared_auth = AuthService(engine, AuthSettings(mode="local"))
    shared_client = TestClient(
        create_app(engine, shared_auth),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    shared_client.app.state.engine = SimpleNamespace(
        dialect=SimpleNamespace(name="sqlite"),
        url=make_url("sqlite:///shared.db?cache=shared"),
    )

    blocked = shared_client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"})

    assert blocked.status_code == 409
    assert "shared" in blocked.json()["detail"].lower()


def test_update_admin_routes_are_owner_only_and_local_only(tmp_path):
    client, _, auth = oidc_api(tmp_path)
    viewer, tokens = login(client, auth, "viewer@example.test", "viewer")
    auth.update_user(viewer.user_id or 0, role="operator", accounts=["CHIISTORE"])

    assert client.get("/api/v1/admin/update").status_code == 403
    assert client.get("/api/v1/admin/update/progress").status_code == 403
    assert client.post(
        "/api/v1/admin/update/install",
        json={"confirmation": "CAP NHAT UNG DUNG"},
        headers={"X-CSRF-Token": tokens.csrf_token},
    ).status_code == 403

    _, owner_tokens = login(client, auth, "owner@example.test", "owner")
    assert client.get("/api/v1/admin/update").status_code == 409
    assert client.get("/api/v1/admin/update/progress").status_code == 409
    assert client.post(
        "/api/v1/admin/update/install",
        json={"confirmation": "CAP NHAT UNG DUNG"},
        headers={"X-CSRF-Token": owner_tokens.csrf_token},
    ).status_code == 409



def _backup_current_db(engine, label="manual"):
    db_path = reset_data_module.sqlite_file_path(engine)
    path = reset_data_module._backup_path(db_path, label)
    reset_data_module._backup_sqlite(db_path, path)
    reset_data_module._check_backup(path)
    return path


def test_restore_backup_lists_previews_and_rejects_traversal_or_bad_files(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    backup_path = _backup_current_db(engine)
    _, tokens = login(client, auth, "owner@example.test", "owner")
    headers = {"X-CSRF-Token": tokens.csrf_token}

    listed = client.get("/api/v1/admin/backups")
    preview = client.get(f"/api/v1/admin/backups/{backup_path.name}/preview")
    traversal = client.get("/api/v1/admin/backups/..%2Fevil.db/preview")
    corrupted = backup_path.with_name(f"{backup_path.stem}-bad{backup_path.suffix}")
    corrupted.write_bytes(b"not sqlite")
    bad_preview = client.get(f"/api/v1/admin/backups/{corrupted.name}/preview")
    wrong_schema = backup_path.with_name(f"{backup_path.stem}-wrong{backup_path.suffix}")
    with sqlite3.connect(wrong_schema) as conn:
        conn.execute("create table import_batches (id integer primary key)")
    wrong_preview = client.get(f"/api/v1/admin/backups/{wrong_schema.name}/preview")

    assert listed.status_code == 200
    listed_item = listed.json()["items"][0]
    assert listed_item["id"] == backup_path.name
    assert listed_item["filename"] == backup_path.name
    assert listed_item["size_bytes"] > 0
    assert listed_item["created_at"]
    assert listed_item["valid"] is True
    assert listed_item["counts"]["business"]["import_batches"] == 1
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["filename"] == backup_path.name
    assert payload["size"] > 0
    assert payload["counts"]["business"]["import_batches"] == 1
    assert payload["counts"]["auth"]["app_users"] == 0
    assert traversal.status_code == 422
    assert bad_preview.status_code == 422
    assert wrong_preview.status_code == 422
    validity = {item["id"]: item["valid"] for item in client.get("/api/v1/admin/backups").json()["items"]}
    assert validity[backup_path.name] is True
    assert validity[corrupted.name] is False
    assert validity[wrong_schema.name] is False
    assert client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": "../evil.db", "confirmation": "KHOI PHUC DU LIEU"},
        headers=headers,
    ).status_code == 422


def test_restore_backup_requires_owner_csrf_phrase_preserves_auth_and_makes_safety_backup(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    backup_path = _backup_current_db(engine)
    import_rows(
        engine,
        filename="b.xlsx",
        file_bytes=b"b",
        account="CHIISTORE",
        rows=[normalized(**{"ID đơn hàng": "O2", "ID SKU": "S2"})],
    )
    owner, tokens = login(client, auth, "owner@example.test", "owner")
    viewer, viewer_tokens = login(client, auth, "viewer@example.test", "viewer")
    auth.update_user(viewer.user_id or 0, role="operator", accounts=["CHIISTORE"])
    headers = {"X-CSRF-Token": tokens.csrf_token}
    client.cookies.set(auth.settings.cookie_name, tokens.session_token)
    client.cookies.set(auth.settings.csrf_cookie_name, tokens.csrf_token)

    assert client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": backup_path.name, "confirmation": "KHOI PHUC DU LIEU"},
    ).status_code == 403
    assert client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": backup_path.name, "confirmation": "KHOI PHUC DU LIEU"},
        headers={"X-CSRF-Token": viewer_tokens.csrf_token},
    ).status_code == 403
    assert client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": backup_path.name, "confirmation": "XOA DU LIEU"},
        headers=headers,
    ).status_code == 422

    restored = client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": backup_path.name, "confirmation": "KHOI PHUC DU LIEU"},
        headers=headers,
    )

    assert restored.status_code == 200
    payload = restored.json()
    safety_path = Path(payload["safety_backup_path"])
    assert safety_path.exists()
    assert safety_path.parent.name == "backups"
    assert set(payload) == {"restored_counts", "safety_backup_path"}
    assert payload["restored_counts"]["import_batches"] == 1
    assert payload["restored_counts"]["order_line_versions"] == 1
    assert client.get("/auth/me").json()["email"] == owner.email
    with engine.connect() as conn:
        batches = conn.execute(select(import_batches.c.filename).order_by(import_batches.c.id)).scalars().all()
        current_orders = conn.execute(select(order_line_versions.c.order_id).order_by(order_line_versions.c.id)).scalars().all()
        assert _count(conn, app_users) == 2
        assert _count(conn, auth_sessions) == 2
    assert batches == ["a.xlsx"]
    assert current_orders == ["O1"]
    with sqlite3.connect(safety_path) as conn:
        assert conn.execute("select count(*) from import_batches").fetchone() == (2,)
    assert client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": backup_path.name, "confirmation": "KHOI PHUC DU LIEU"},
        headers=headers,
    ).status_code == 200


def test_restore_backup_rolls_back_business_tables_on_failure(tmp_path, monkeypatch):
    client, engine, auth = oidc_api(tmp_path)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[normalized()])
    backup_path = _backup_current_db(engine)
    import_rows(
        engine,
        filename="b.xlsx",
        file_bytes=b"b",
        account="CHIISTORE",
        rows=[normalized(**{"ID đơn hàng": "O2", "ID SKU": "S2"})],
    )
    _, tokens = login(client, auth, "owner@example.test", "owner")

    def fail_after_delete(conn, _backup_path):
        conn.exec_driver_sql('DELETE FROM "raw_import_rows"')
        conn.exec_driver_sql('DELETE FROM "order_line_versions"')
        raise RuntimeError("forced restore failure")

    monkeypatch.setattr(reset_data_module, "_replace_business_tables", fail_after_delete)

    failed = client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": backup_path.name, "confirmation": "KHOI PHUC DU LIEU"},
        headers={"X-CSRF-Token": tokens.csrf_token},
    )

    assert failed.status_code == 500
    with engine.connect() as conn:
        assert conn.execute(select(import_batches.c.filename).order_by(import_batches.c.id)).scalars().all() == ["a.xlsx", "b.xlsx"]
        assert conn.execute(select(order_line_versions.c.order_id).order_by(order_line_versions.c.id)).scalars().all() == ["O1", "O2"]
