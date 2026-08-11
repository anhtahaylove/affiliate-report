from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoResultFound

from .accounts import active_account_codes
from .db import app_users, auth_sessions, oidc_login_states, user_account_access, user_ui_preferences, saved_report_views

ROLES = {"owner", "operator", "viewer"}


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass(frozen=True)
class AuthSettings:
    mode: str = "local"
    cookie_name: str = "tt_affiliate_session"
    csrf_cookie_name: str = "csrf_token"
    cookie_secure: bool = True
    web_app_url: str = "http://127.0.0.1:3000"
    session_ttl_seconds: int = 8 * 60 * 60
    state_ttl_seconds: int = 10 * 60
    oidc_issuer: str | None = None
    oidc_metadata_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str | None = None
    bootstrap_owner_email: str | None = None
    allowed_emails: tuple[str, ...] = ()
    default_role: str = "viewer"
    default_accounts: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "AuthSettings":
        mode = os.getenv("AUTH_MODE", "local").strip().lower()
        if mode not in {"local", "oidc"}:
            raise ValueError("AUTH_MODE phải là local hoặc oidc.")
        default_role = os.getenv("AUTH_DEFAULT_ROLE", "viewer").strip().lower()
        if default_role not in ROLES - {"owner"}:
            raise ValueError("AUTH_DEFAULT_ROLE phải là operator hoặc viewer.")
        accounts = tuple(_csv(os.getenv("AUTH_DEFAULT_ACCOUNTS")))
        settings = cls(
            mode=mode,
            cookie_name=os.getenv("AUTH_SESSION_COOKIE", "tt_affiliate_session").strip() or "tt_affiliate_session",
            csrf_cookie_name=os.getenv("AUTH_CSRF_COOKIE", "csrf_token").strip() or "csrf_token",
            cookie_secure=os.getenv("AUTH_COOKIE_SECURE", "true").strip().lower() not in {"0", "false", "no"},
            web_app_url=os.getenv("WEB_APP_URL", "http://127.0.0.1:3000").strip() or "http://127.0.0.1:3000",
            session_ttl_seconds=int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(8 * 60 * 60))),
            state_ttl_seconds=int(os.getenv("OIDC_STATE_TTL_SECONDS", str(10 * 60))),
            oidc_issuer=os.getenv("OIDC_ISSUER"),
            oidc_metadata_url=os.getenv("OIDC_METADATA_URL"),
            oidc_client_id=os.getenv("OIDC_CLIENT_ID"),
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET"),
            oidc_redirect_uri=os.getenv("OIDC_REDIRECT_URI"),
            bootstrap_owner_email=(os.getenv("AUTH_BOOTSTRAP_OWNER_EMAIL") or "").strip().lower() or None,
            allowed_emails=tuple(email.lower() for email in _csv(os.getenv("AUTH_ALLOWED_EMAILS"))),
            default_role=default_role,
            default_accounts=accounts,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.session_ttl_seconds <= 0 or self.state_ttl_seconds <= 0:
            raise ValueError("Auth TTL phải lớn hơn 0.")
        if self.mode == "oidc":
            metadata_url = self.oidc_metadata_url or (self.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration" if self.oidc_issuer else None)
            missing = [
                name
                for name, value in {
                    "OIDC_CLIENT_ID": self.oidc_client_id,
                    "OIDC_REDIRECT_URI": self.oidc_redirect_uri,
                    "OIDC_METADATA_URL or OIDC_ISSUER": metadata_url,
                    "AUTH_BOOTSTRAP_OWNER_EMAIL": self.bootstrap_owner_email,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("Thiếu cấu hình OIDC: " + ", ".join(missing))


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    email: str
    display_name: str | None
    role: str
    active: bool
    accounts: tuple[str, ...]
    auth_method: str
    auth_subject: str

    def can_access_account(self, account: str) -> bool:
        return self.role == "owner" or account in self.accounts


@dataclass(frozen=True)
class SessionTokens:
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class OidcLogin:
    authorization_url: str
    state: str
    expires_at: datetime


class AuthService:
    def __init__(self, engine: Engine, settings: AuthSettings | None = None):
        self.engine = engine
        self.settings = settings or AuthSettings.from_env()

    def local_principal(self) -> Principal:
        return Principal(
            user_id=None,
            email="local-owner@localhost",
            display_name="Local owner",
            role="owner",
            active=True,
            accounts=self._account_codes(),
            auth_method="local",
            auth_subject="local-owner",
        )

    def get_principal(self, session_token: str | None) -> Principal | None:
        return self.principal_from_session(session_token)

    def require_csrf(self, session_token: str | None, csrf_token: str | None) -> bool:
        return self.verify_csrf(session_token, csrf_token)

    def create_login_url(self) -> OidcLogin:
        return self.start_oidc_login()

    async def acreate_login_url(self) -> OidcLogin:
        return await self.astart_oidc_login()

    def finish_login(self, *, code: str, state: str) -> tuple[Principal, str, str]:
        principal, tokens = self.complete_oidc_callback(state=state, code=code)
        return principal, tokens.session_token, tokens.csrf_token

    async def afinish_login(self, *, code: str, state: str) -> tuple[Principal, str, str]:
        principal, tokens = await self.acomplete_oidc_callback(state=state, code=code)
        return principal, tokens.session_token, tokens.csrf_token

    def revoke_session(self, session_token: str | None) -> None:
        self.logout(session_token)

    @staticmethod
    def principal_key(principal: Principal) -> str:
        return f"user:{principal.user_id}" if principal.user_id is not None else "local:local-owner"

    def get_preferences(self, principal: Principal) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(user_ui_preferences).where(
                    user_ui_preferences.c.principal_key == self.principal_key(principal)
                )
            ).mappings().one_or_none()
        if row is None:
            return None
        return {
            "theme": row["theme"],
            "sidebar_collapsed": bool(row["sidebar_collapsed"]),
            "dashboard_layout": row["dashboard_layout_json"],
            "updated_at": row["updated_at"],
        }

    def save_preferences(self, principal: Principal, values: dict[str, Any]) -> None:
        key = self.principal_key(principal)
        stored = {
            "theme": values["theme"],
            "sidebar_collapsed": bool(values["sidebar_collapsed"]),
            "dashboard_layout_json": values["dashboard_layout"],
            "updated_at": func.now(),
        }
        with self.engine.begin() as conn:
            existing = conn.execute(select(user_ui_preferences.c.principal_key).where(user_ui_preferences.c.principal_key == key)).first()
            if existing:
                conn.execute(update(user_ui_preferences).where(user_ui_preferences.c.principal_key == key).values(**stored))
            else:
                conn.execute(user_ui_preferences.insert().values(principal_key=key, app_user_id=principal.user_id, **stored))

    def list_views(self, principal: Principal, route: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(saved_report_views).where(
                    saved_report_views.c.principal_key == self.principal_key(principal),
                    saved_report_views.c.route == route,
                ).order_by(saved_report_views.c.is_default.desc(), saved_report_views.c.name)
            ).mappings().all()
        return [self._saved_view_public(row) for row in rows]

    def get_view(self, principal: Principal, view_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(saved_report_views).where(
                    saved_report_views.c.id == view_id,
                    saved_report_views.c.principal_key == self.principal_key(principal),
                )
            ).mappings().one_or_none()
        return self._saved_view_public(row) if row is not None else None

    def create_view(self, principal: Principal, route: str, name: str, filters: dict[str, Any], is_default: bool = False) -> dict[str, Any]:
        key = self.principal_key(principal)
        with self.engine.begin() as conn:
            count = conn.execute(
                select(func.count()).select_from(saved_report_views).where(saved_report_views.c.principal_key == key)
            ).scalar_one()
            if count >= 50:
                raise ValueError("saved view limit exceeded")
            if is_default:
                conn.execute(
                    update(saved_report_views)
                    .where(saved_report_views.c.principal_key == key, saved_report_views.c.route == route)
                    .values(is_default=False, updated_at=func.now())
                )
            result = conn.execute(
                saved_report_views.insert().values(
                    principal_key=key,
                    app_user_id=principal.user_id,
                    route=route,
                    name=name,
                    filters_json=filters,
                    is_default=is_default,
                )
            )
            view_id = result.inserted_primary_key[0]
            row = conn.execute(select(saved_report_views).where(saved_report_views.c.id == view_id)).mappings().one()
        return self._saved_view_public(row)

    def update_view(
        self,
        principal: Principal,
        view_id: int,
        *,
        name: str | None = None,
        filters: dict[str, Any] | None = None,
        is_default: bool | None = None,
    ) -> dict[str, Any] | None:
        key = self.principal_key(principal)
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(saved_report_views).where(
                    saved_report_views.c.id == view_id,
                    saved_report_views.c.principal_key == key,
                )
            ).mappings().one_or_none()
            if existing is None:
                return None
            if is_default:
                conn.execute(
                    update(saved_report_views)
                    .where(
                        saved_report_views.c.principal_key == key,
                        saved_report_views.c.route == existing["route"],
                    )
                    .values(is_default=False, updated_at=func.now())
                )
            changes: dict[str, Any] = {"updated_at": func.now()}
            if name is not None:
                changes["name"] = name
            if filters is not None:
                changes["filters_json"] = filters
            if is_default is not None:
                changes["is_default"] = is_default
            conn.execute(
                update(saved_report_views)
                .where(saved_report_views.c.id == view_id, saved_report_views.c.principal_key == key)
                .values(**changes)
            )
            row = conn.execute(select(saved_report_views).where(saved_report_views.c.id == view_id)).mappings().one()
        return self._saved_view_public(row)

    def delete_view(self, principal: Principal, view_id: int) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(delete(saved_report_views).where(saved_report_views.c.id == view_id, saved_report_views.c.principal_key == self.principal_key(principal)))
        return bool(result.rowcount)

    @staticmethod
    def _saved_view_public(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "route": row["route"],
            "name": row["name"],
            "filters": row["filters_json"],
            "is_default": bool(row["is_default"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_users(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(app_users).order_by(app_users.c.id)).mappings().all()
            accounts = {
                row["id"]: tuple(conn.execute(
                    select(user_account_access.c.account).where(user_account_access.c.user_id == row["id"])
                ).scalars().all())
                for row in rows
            }
        return [
            {
                "id": row["id"],
                "email": row["email"],
                "display_name": row["display_name"],
                "role": row["role"],
                "active": row["active"],
                "accounts": self._account_codes() if row["role"] == "owner" else accounts[row["id"]],
            }
            for row in rows
        ]

    def update_user(
        self,
        user_id: int,
        *,
        role: str | None = None,
        accounts: tuple[str, ...] | list[str] | None = None,
        active: bool | None = None,
    ) -> Principal:
        if role is not None and role not in ROLES:
            raise ValueError("role phải là owner, operator hoặc viewer.")
        if accounts is not None:
            accounts = tuple(dict.fromkeys(accounts))
        valid_accounts = set(self._account_codes())
        if accounts is not None and (set(accounts) - valid_accounts):
            raise ValueError("accounts chứa account không hợp lệ.")
        with self.engine.begin() as conn:
            values: dict[str, Any] = {"updated_at": func.now()}
            if role is not None:
                values["role"] = role
            if active is not None:
                values["active"] = active
            result = conn.execute(update(app_users).where(app_users.c.id == user_id).values(**values))
            if result.rowcount == 0:
                raise LookupError("Không tìm thấy user.")
            if accounts is not None:
                conn.execute(delete(user_account_access).where(user_account_access.c.user_id == user_id))
                for account in accounts:
                    conn.execute(user_account_access.insert().values(user_id=user_id, account=account))
            if active is False:
                conn.execute(delete(auth_sessions).where(auth_sessions.c.user_id == user_id))
            return self._principal(conn, user_id)

    def start_oidc_login(self) -> OidcLogin:
        return asyncio.run(self.astart_oidc_login())

    async def astart_oidc_login(self) -> OidcLogin:
        self.settings.validate()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        nonce = secrets.token_urlsafe(32)
        expires_at = _now() + timedelta(seconds=self.settings.state_ttl_seconds)
        with self.engine.begin() as conn:
            conn.execute(delete(oidc_login_states).where(oidc_login_states.c.expires_at < _now()))
            conn.execute(oidc_login_states.insert().values(
                state_hash=_hash(state),
                code_verifier=verifier,
                nonce=nonce,
                expires_at=expires_at,
            ))
        return OidcLogin(await self._authorization_url(state, verifier, nonce), state, expires_at)

    def complete_oidc_callback(self, *, state: str, code: str) -> tuple[Principal, SessionTokens]:
        return asyncio.run(self.acomplete_oidc_callback(state=state, code=code))

    async def acomplete_oidc_callback(self, *, state: str, code: str) -> tuple[Principal, SessionTokens]:
        row = self._pop_state(state)
        app = self._oidc_app()
        token = await app.fetch_access_token(
            redirect_uri=self.settings.oidc_redirect_uri,
            code=code,
            code_verifier=row["code_verifier"],
        )
        claims_options = {"iss": {"values": [self.settings.oidc_issuer]}} if self.settings.oidc_issuer else None
        claims = dict(await app.parse_id_token(token, nonce=row["nonce"], claims_options=claims_options))
        if self.settings.oidc_issuer and claims.get("iss") != self.settings.oidc_issuer:
            raise PermissionError("OIDC issuer không hợp lệ.")
        if claims.get("email_verified") is False:
            raise PermissionError("OIDC email chưa được xác minh.")
        principal = self.provision_user(
            issuer=str(claims.get("iss") or self.settings.oidc_issuer or ""),
            subject=str(claims.get("sub") or ""),
            email=str(claims.get("email") or "").lower(),
            display_name=claims.get("name"),
        )
        return principal, self.create_session(principal)

    def provision_user(self, *, issuer: str, subject: str, email: str, display_name: str | None = None) -> Principal:
        email = email.strip().lower()
        if not issuer or not subject or not email:
            raise ValueError("OIDC profile thiếu issuer, subject hoặc email.")
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(app_users).where(app_users.c.issuer == issuer, app_users.c.subject == subject)
            ).mappings().first()
            if existing:
                if not existing["active"]:
                    raise PermissionError("Tài khoản đã bị vô hiệu hóa.")
                conn.execute(update(app_users).where(app_users.c.id == existing["id"]).values(
                    email=email,
                    display_name=display_name,
                    last_login_at=func.now(),
                    updated_at=func.now(),
                ))
                return self._principal(conn, existing["id"], email=email, display_name=display_name)

            role = "owner" if email == self.settings.bootstrap_owner_email else self.settings.default_role
            allowed = email == self.settings.bootstrap_owner_email or email in self.settings.allowed_emails
            if not allowed:
                raise PermissionError("Email không nằm trong allowlist.")
            user_id = conn.execute(app_users.insert().values(
                issuer=issuer,
                subject=subject,
                email=email,
                display_name=display_name,
                role=role,
                active=True,
                last_login_at=func.now(),
            )).inserted_primary_key[0]
            valid_accounts = set(self._account_codes())
            if set(self.settings.default_accounts) - valid_accounts:
                raise ValueError("AUTH_DEFAULT_ACCOUNTS chứa account không hợp lệ.")
            accounts = self._account_codes() if role == "owner" else self.settings.default_accounts
            for account in accounts:
                conn.execute(user_account_access.insert().values(user_id=user_id, account=account))
            return self._principal(conn, user_id, email=email, display_name=display_name)

    def create_session(self, principal: Principal) -> SessionTokens:
        if principal.user_id is None:
            raise ValueError("Local principal không cần DB session.")
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = _now() + timedelta(seconds=self.settings.session_ttl_seconds)
        with self.engine.begin() as conn:
            conn.execute(delete(auth_sessions).where(auth_sessions.c.expires_at < _now()))
            conn.execute(auth_sessions.insert().values(
                token_hash=_hash(session_token),
                user_id=principal.user_id,
                csrf_hash=_hash(csrf_token),
                expires_at=expires_at,
            ))
        return SessionTokens(session_token, csrf_token, expires_at)

    def principal_from_session(self, session_token: str | None) -> Principal | None:
        if self.settings.mode == "local":
            return self.local_principal()
        if not session_token:
            return None
        with self.engine.begin() as conn:
            row = conn.execute(
                select(auth_sessions, app_users.c.active)
                .join(app_users, app_users.c.id == auth_sessions.c.user_id)
                .where(auth_sessions.c.token_hash == _hash(session_token))
            ).mappings().first()
            if not row or _aware(row["expires_at"]) <= _now() or not row["active"]:
                if row:
                    conn.execute(delete(auth_sessions).where(auth_sessions.c.token_hash == row["token_hash"]))
                return None
            return self._principal(conn, row["user_id"])

    def verify_csrf(self, session_token: str | None, csrf_token: str | None) -> bool:
        if self.settings.mode == "local":
            return True
        if not session_token or not csrf_token:
            return False
        with self.engine.connect() as conn:
            row = conn.execute(
                select(auth_sessions.c.csrf_hash, auth_sessions.c.expires_at)
                .where(auth_sessions.c.token_hash == _hash(session_token))
            ).mappings().first()
        return bool(row and _aware(row["expires_at"]) > _now() and secrets.compare_digest(row["csrf_hash"], _hash(csrf_token)))

    def logout(self, session_token: str | None) -> None:
        if session_token:
            with self.engine.begin() as conn:
                conn.execute(delete(auth_sessions).where(auth_sessions.c.token_hash == _hash(session_token)))

    def cookie_options(self, expires_at: datetime | None = None) -> dict[str, Any]:
        options: dict[str, Any] = {
            "key": self.settings.cookie_name,
            "httponly": True,
            "secure": self.settings.cookie_secure,
            "samesite": "lax",
            "path": "/",
            "max_age": self.settings.session_ttl_seconds,
        }
        if expires_at:
            options["expires"] = expires_at
        return options

    async def _authorization_url(self, state: str, verifier: str, nonce: str) -> str:
        from authlib.oauth2.rfc7636 import create_s256_code_challenge

        data = await self._oidc_app().create_authorization_url(
            self.settings.oidc_redirect_uri,
            response_type="code",
            scope="openid email profile",
            state=state,
            nonce=nonce,
            code_challenge=create_s256_code_challenge(verifier),
            code_challenge_method="S256",
        )
        return data["url"]

    def _oidc_app(self):
        from authlib.integrations.starlette_client import StarletteOAuth2App

        metadata_url = self.settings.oidc_metadata_url or (self.settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration" if self.settings.oidc_issuer else None)
        return StarletteOAuth2App(
            None,
            name="oidc",
            client_id=self.settings.oidc_client_id,
            client_secret=self.settings.oidc_client_secret,
            server_metadata_url=metadata_url,
            client_kwargs={"scope": "openid email profile"},
        )

    def _pop_state(self, state: str) -> dict[str, Any]:
        state_hash = _hash(state)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(oidc_login_states).where(oidc_login_states.c.state_hash == state_hash)
            ).mappings().first()
            conn.execute(delete(oidc_login_states).where(oidc_login_states.c.state_hash == state_hash))
            if not row or _aware(row["expires_at"]) <= _now():
                raise ValueError("OIDC state không hợp lệ hoặc đã hết hạn.")
            return dict(row)

    def _principal(
        self,
        conn,
        user_id: int,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> Principal:
        try:
            user = conn.execute(select(app_users).where(app_users.c.id == user_id)).mappings().one()
        except NoResultFound as exc:
            raise LookupError("Không tìm thấy user.") from exc
        accounts = tuple(
            conn.execute(
                select(user_account_access.c.account).where(user_account_access.c.user_id == user_id)
            ).scalars().all()
        )
        return Principal(
            user_id=user_id,
            email=email or user["email"],
            display_name=display_name if display_name is not None else user["display_name"],
            role=user["role"],
            active=bool(user["active"]),
            accounts=self._account_codes() if user["role"] == "owner" else accounts,
            auth_method="oidc",
            auth_subject=f"{user['issuer']}:{user['subject']}",
        )

    def _account_codes(self) -> tuple[str, ...]:
        return active_account_codes(self.engine)
