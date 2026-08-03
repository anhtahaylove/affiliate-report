from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from tiktok_affiliate_report.auth import AuthService, AuthSettings, _hash
from tiktok_affiliate_report.db import auth_sessions, get_engine, init_db, oidc_login_states


def service(tmp_path, **updates):
    engine = get_engine(f"sqlite:///{(tmp_path / 'auth.db').as_posix()}")
    init_db(engine)
    values = {
        "mode": "oidc",
        "oidc_client_id": "client",
        "oidc_issuer": "http://idp.test",
        "oidc_redirect_uri": "http://app.test/auth/callback",
        "bootstrap_owner_email": "owner@example.com",
        "allowed_emails": ("owner@example.com", "viewer@example.com"),
        "default_accounts": ("CHIISTORE",),
    } | updates
    settings = AuthSettings(**values)
    return AuthService(engine, settings), engine


def test_settings_from_env_validates_oidc(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "http://idp.test")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "http://app.test/callback")
    monkeypatch.setenv("AUTH_BOOTSTRAP_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", "viewer@example.com")

    settings = AuthSettings.from_env()

    assert settings.mode == "oidc"
    assert settings.allowed_emails == ("viewer@example.com",)
    assert settings.default_accounts == ()


def test_local_mode_returns_owner_without_db_session(tmp_path):
    auth, _ = service(tmp_path, mode="local")

    principal = auth.principal_from_session(None)

    assert principal.email == "local-owner@localhost"
    assert principal.role == "owner"
    assert principal.can_access_account("THAOBRA")
    assert auth.verify_csrf(None, None) is True


class FakeOidcApp:
    def __init__(self, claims=None, error=None):
        self.claims = claims or {
            "iss": "http://idp.test",
            "sub": "subject-1",
            "email": "owner@example.com",
            "email_verified": True,
        }
        self.error = error

    async def create_authorization_url(self, redirect_uri, **kwargs):
        return {"url": f"http://idp.test/auth?state={kwargs['state']}&code_challenge_method={kwargs['code_challenge_method']}"}

    async def fetch_access_token(self, **kwargs):
        return {"id_token": "signed-id-token"}

    async def parse_id_token(self, token, nonce, claims_options=None):
        if self.error:
            raise self.error
        return self.claims


def test_start_oidc_login_stores_only_state_hash_and_pkce_server_side(tmp_path, monkeypatch):
    auth, engine = service(tmp_path)
    monkeypatch.setattr(auth, "_oidc_app", lambda: FakeOidcApp())

    login = auth.start_oidc_login()
    qs = parse_qs(urlparse(login.authorization_url).query)

    assert qs["state"] == [login.state]
    assert qs["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in login.authorization_url
    with engine.connect() as conn:
        row = conn.execute(select(oidc_login_states)).mappings().one()
    assert row["state_hash"] != login.state
    assert len(row["state_hash"]) == 64
    assert row["code_verifier"]
    assert row["nonce"]


def test_provision_bootstrap_owner_allowed_viewer_and_rejects_unknown(tmp_path):
    auth, _ = service(tmp_path)

    owner = auth.provision_user(issuer="idp", subject="1", email="owner@example.com", display_name="Owner")
    viewer = auth.provision_user(issuer="idp", subject="2", email="viewer@example.com")

    assert owner.role == "owner"
    assert owner.can_access_account("EMLINHNOIY")
    assert viewer.role == "viewer"
    assert viewer.accounts == ("CHIISTORE",)
    with pytest.raises(PermissionError):
        auth.provision_user(issuer="idp", subject="3", email="stranger@example.com")


def test_session_cookie_hash_csrf_lookup_and_logout(tmp_path):
    auth, engine = service(tmp_path)
    principal = auth.provision_user(issuer="idp", subject="1", email="owner@example.com")

    tokens = auth.create_session(principal)
    loaded = auth.principal_from_session(tokens.session_token)

    assert loaded.email == "owner@example.com"
    assert auth.verify_csrf(tokens.session_token, tokens.csrf_token) is True
    assert auth.verify_csrf(tokens.session_token, "bad") is False
    assert auth.cookie_options(tokens.expires_at) | {"expires": tokens.expires_at} == {
        "key": "tt_affiliate_session",
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "path": "/",
        "max_age": 28800,
        "expires": tokens.expires_at,
    }
    with engine.connect() as conn:
        row = conn.execute(select(auth_sessions)).mappings().one()
    assert row["token_hash"] != tokens.session_token
    assert row["csrf_hash"] != tokens.csrf_token

    auth.logout(tokens.session_token)

    assert auth.principal_from_session(tokens.session_token) is None


def test_public_api_aliases_and_user_admin(tmp_path):
    auth, _ = service(tmp_path)
    principal = auth.provision_user(issuer="idp", subject="1", email="owner@example.com")
    tokens = auth.create_session(principal)

    assert auth.get_principal(tokens.session_token).email == "owner@example.com"
    assert auth.require_csrf(tokens.session_token, tokens.csrf_token) is True
    assert auth.list_users()[0]["accounts"] == ("CHIISTORE", "EMLINHNOIY", "THAOBRA")

    updated = auth.update_user(principal.user_id, role="operator", accounts=("THAOBRA",))

    assert updated.role == "operator"
    assert updated.accounts == ("THAOBRA",)
    auth.revoke_session(tokens.session_token)
    assert auth.get_principal(tokens.session_token) is None


def test_finish_login_validates_id_token_claims(tmp_path, monkeypatch):
    auth, _ = service(tmp_path)
    monkeypatch.setattr(auth, "_oidc_app", lambda: FakeOidcApp())
    login = auth.start_oidc_login()

    principal, session_token, csrf_token = auth.finish_login(code="code", state=login.state)

    assert principal.email == "owner@example.com"
    assert session_token
    assert csrf_token


def test_finish_login_rejects_wrong_issuer_and_nonce_error(tmp_path, monkeypatch):
    auth, _ = service(tmp_path)
    monkeypatch.setattr(auth, "_oidc_app", lambda: FakeOidcApp(claims={
        "iss": "http://evil.test",
        "sub": "subject-1",
        "email": "owner@example.com",
        "email_verified": True,
    }))
    login = auth.start_oidc_login()
    with pytest.raises(PermissionError):
        auth.finish_login(code="code", state=login.state)

    auth2, _ = service(tmp_path / "nonce")
    monkeypatch.setattr(auth2, "_oidc_app", lambda: FakeOidcApp(error=ValueError("bad nonce")))
    login2 = auth2.start_oidc_login()
    with pytest.raises(ValueError, match="bad nonce"):
        auth2.finish_login(code="code", state=login2.state)


def test_disabled_user_session_is_revoked(tmp_path):
    auth, _ = service(tmp_path)
    principal = auth.provision_user(issuer="idp", subject="1", email="owner@example.com")
    tokens = auth.create_session(principal)

    auth.update_user(principal.user_id, active=False)

    assert auth.get_principal(tokens.session_token) is None


def test_expired_session_is_removed(tmp_path):
    auth, engine = service(tmp_path)
    principal = auth.provision_user(issuer="idp", subject="1", email="owner@example.com")
    token = "expired-session"
    with engine.begin() as conn:
        conn.execute(auth_sessions.insert().values(
            token_hash=_hash(token),
            user_id=principal.user_id,
            csrf_hash="csrf",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ))

    assert auth.principal_from_session(token) is None
    with engine.connect() as conn:
        assert conn.execute(select(auth_sessions)).first() is None
