from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_api import normalized, raw_export_row, xlsx_bytes
from tiktok_affiliate_report.api import create_app
from tiktok_affiliate_report.auth import AuthService, AuthSettings
from tiktok_affiliate_report.db import get_engine, import_batches, import_rows


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
    return TestClient(create_app(engine, auth)), engine, auth


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
