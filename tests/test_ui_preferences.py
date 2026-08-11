from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from tests.test_api_auth import login, oidc_api
from tiktok_affiliate_report.api import create_app
from tiktok_affiliate_report.auth import AuthService, AuthSettings
from tiktok_affiliate_report.db import app_users, get_engine, saved_report_views, user_ui_preferences


DEFAULT_WIDGETS = [
    "today_pulse",
    "target_progress",
    "action_alerts",
    "trend",
    "account_contribution",
    "settlement",
    "data_freshness",
    "recent_imports",
]


def local_api(tmp_path):
    engine = get_engine(f"sqlite:///{(tmp_path / 'local-ui.db').as_posix()}")
    app = create_app(engine, AuthService(engine, AuthSettings(mode="local")))
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)), engine


def test_local_preferences_defaults_validate_and_persist(tmp_path):
    client, _ = local_api(tmp_path)

    defaults = client.get("/api/v1/ui/preferences")
    assert defaults.status_code == 200
    assert defaults.json()["theme"] == "system"
    assert defaults.json()["dashboard_layout"]["order"] == DEFAULT_WIDGETS

    invalid = client.patch(
        "/api/v1/ui/preferences",
        json={"dashboard_layout": {"schema": 1, "order": ["today_pulse"], "hidden": []}},
    )
    assert invalid.status_code == 422

    updated = client.patch(
        "/api/v1/ui/preferences",
        json={
            "theme": "dark",
            "sidebar_collapsed": True,
            "dashboard_layout": {"schema": 1, "order": list(reversed(DEFAULT_WIDGETS)), "hidden": ["recent_imports"]},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["theme"] == "dark"
    assert updated.json()["sidebar_collapsed"] is True
    assert client.get("/api/v1/ui/preferences").json()["dashboard_layout"]["hidden"] == ["recent_imports"]


def test_saved_views_are_csrf_protected_scoped_and_sanitized(tmp_path):
    client, _, auth = oidc_api(tmp_path)
    _, owner_tokens = login(client, auth, "owner@example.test", "owner")
    payload = {
        "route": "orders",
        "name": "  Đơn cần kiểm tra  ",
        "filters": {"schema": 1, "account": ["CHIISTORE"], "status": ["pending"], "size": 50},
        "is_default": True,
    }

    assert client.post("/api/v1/ui/saved-views", json=payload).status_code == 403
    created = client.post(
        "/api/v1/ui/saved-views",
        json=payload,
        headers={"X-CSRF-Token": owner_tokens.csrf_token},
    )
    assert created.status_code == 200
    view_id = created.json()["id"]
    assert created.json()["name"] == "Đơn cần kiểm tra"
    assert client.post(
        "/api/v1/ui/saved-views",
        json={**payload, "name": "Không hợp lệ", "filters": {"unknown": True}},
        headers={"X-CSRF-Token": owner_tokens.csrf_token},
    ).status_code == 422
    assert client.post(
        "/api/v1/ui/saved-views",
        json={**payload, "name": "Trạng thái sai", "filters": {"status": ["settled", "mystery"]}},
        headers={"X-CSRF-Token": owner_tokens.csrf_token},
    ).status_code == 422
    assert client.post(
        "/api/v1/ui/saved-views",
        json={**payload, "name": "Account sai", "filters": {"account": ["all"]}},
        headers={"X-CSRF-Token": owner_tokens.csrf_token},
    ).status_code == 422
    assert client.post(
        "/api/v1/ui/saved-views",
        json=payload,
        headers={"X-CSRF-Token": owner_tokens.csrf_token},
    ).status_code == 409
    second = client.post(
        "/api/v1/ui/saved-views",
        json={**payload, "name": "Mặc định mới"},
        headers={"X-CSRF-Token": owner_tokens.csrf_token},
    )
    assert second.status_code == 200
    owner_views = client.get("/api/v1/ui/saved-views", params={"route": "orders"}).json()["items"]
    assert [item["name"] for item in owner_views if item["is_default"]] == ["Mặc định mới"]

    _, viewer_tokens = login(client, auth, "viewer@example.test", "viewer")
    assert client.get("/api/v1/ui/saved-views", params={"route": "orders"}).json()["count"] == 0
    assert client.delete(
        f"/api/v1/ui/saved-views/{view_id}",
        headers={"X-CSRF-Token": viewer_tokens.csrf_token},
    ).status_code == 404

    _, owner_tokens = login(client, auth, "owner@example.test", "owner")
    patched = client.patch(
        f"/api/v1/ui/saved-views/{view_id}",
        json={"name": "Đã đối soát", "filters": {"schema": 1, "direction": "desc"}},
        headers={"X-CSRF-Token": owner_tokens.csrf_token},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Đã đối soát"


def test_reset_preserves_preferences_and_restore_recovers_them(tmp_path):
    client, engine = local_api(tmp_path)
    assert client.patch("/api/v1/ui/preferences", json={"theme": "light"}).status_code == 200

    reset = client.post("/api/v1/admin/reset-data", json={"confirmation": "XOA DU LIEU"})
    assert reset.status_code == 200
    assert client.get("/api/v1/ui/preferences").json()["theme"] == "light"
    backup_id = reset.json()["backup_path"].split("\\")[-1].split("/")[-1]

    assert client.patch("/api/v1/ui/preferences", json={"theme": "dark"}).status_code == 200
    restored = client.post(
        "/api/v1/admin/backups/restore",
        json={"backup_id": backup_id, "confirmation": "KHOI PHUC DU LIEU"},
    )
    assert restored.status_code == 200
    assert client.get("/api/v1/ui/preferences").json()["theme"] == "light"


def test_oidc_user_delete_cascades_preferences_and_saved_views(tmp_path):
    client, engine, auth = oidc_api(tmp_path)
    principal, tokens = login(client, auth, "viewer@example.test", "viewer")
    headers = {"X-CSRF-Token": tokens.csrf_token}
    assert client.patch("/api/v1/ui/preferences", json={"theme": "dark"}, headers=headers).status_code == 200
    assert client.post(
        "/api/v1/ui/saved-views",
        json={"route": "dashboard", "name": "Của tôi", "filters": {"schema": 1}},
        headers=headers,
    ).status_code == 200

    with engine.begin() as conn:
        conn.execute(delete(app_users).where(app_users.c.id == principal.user_id))
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(user_ui_preferences)).scalar_one() == 0
        assert conn.execute(select(func.count()).select_from(saved_report_views)).scalar_one() == 0
