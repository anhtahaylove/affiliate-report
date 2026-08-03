from __future__ import annotations

import math
import os
import secrets
import sys
import threading
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.engine import Engine

from .auth import AuthService, AuthSettings, Principal, is_loopback_host
from .db import get_engine, import_batches, import_rows, init_db, monthly_targets
from .parser import DEFAULT_ACCOUNTS, read_xlsx
from .reports import daily_report, monthly_kpi, orders, overview
from .reset_data import (
    RESET_CONFIRMATION_PHRASE,
    RESTORE_CONFIRMATION_PHRASE,
    list_sqlite_backups,
    preview_sqlite_backup,
    reset_sqlite_business_data,
    restore_sqlite_business_backup,
    sqlite_file_path,
)
from .updater import (
    INSTALL_CONFIRMATION_PHRASE,
    UpdateError,
    check_for_update,
    download_latest_update,
    schedule_installer,
)
from .version import APP_VERSION

MAX_UPLOAD_MB = 20
STATUSES = ["settled", "ineligible", "pending", "unknown"]


class UserUpdate(BaseModel):
    role: Literal["owner", "operator", "viewer"] | None = None
    accounts: list[str] | None = None
    active: bool | None = None


class TargetUpdate(BaseModel):
    target_commission: int = Field(ge=0, le=1_000_000_000_000)


class ResetDataRequest(BaseModel):
    confirmation: str


class RestoreBackupRequest(BaseModel):
    backup_id: str
    confirmation: str


class InstallUpdateRequest(BaseModel):
    confirmation: str


def _cors_origins() -> list[str]:
    raw = os.getenv("API_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _items(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: _clean(value) for key, value in row.items()} for row in df.to_dict(orient="records")]


def _list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    out = [part.strip() for value in values for part in value.split(",") if part.strip()]
    return out or None


def _month_start(value: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="month must use YYYY-MM") from exc
    return date(parsed.year, parsed.month, 1)


def _engine(app: FastAPI) -> Engine:
    return app.state.engine


def _auth(app: FastAPI) -> AuthService:
    return app.state.auth


def _web_app_url(auth: AuthService) -> str:
    return getattr(auth.settings, "web_app_url", None) or os.getenv("WEB_APP_URL", "http://127.0.0.1:3000")


def _csrf_cookie_name(auth: AuthService) -> str:
    return getattr(auth.settings, "csrf_cookie_name", "csrf_token")


def _automatic_update_supported(app: FastAPI) -> bool:
    return (
        os.name == "nt"
        and bool(getattr(sys, "frozen", False))
        and callable(getattr(app.state, "update_shutdown", None))
    )


async def _read_upload(file: UploadFile) -> bytes:
    limit = MAX_UPLOAD_MB * 1024 * 1024
    data = bytearray()
    while chunk := await file.read(min(1024 * 1024, limit + 1 - len(data))):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB")
    return bytes(data)


def create_app(engine: Engine | None = None, auth: AuthService | None = None) -> FastAPI:
    app = FastAPI(
        title="TikTok Affiliate Report API",
        description="Phase-2 API with local-safe mode, OIDC sessions and account-scoped RBAC.",
        version=APP_VERSION,
    )
    app.state.engine = engine or get_engine()
    init_db(app.state.engine)
    app.state.auth = auth or AuthService(app.state.engine, AuthSettings.from_env())
    app.state.update_lock = threading.Lock()
    app.state.update_scheduled = False
    origins = _cors_origins()
    if "*" in origins:
        raise ValueError("API_CORS_ORIGINS không được dùng * khi cookie credentials được bật.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
    )

    def principal(request: Request) -> Principal:
        service = _auth(app)
        if service.settings.mode == "local" and (
            request.client is None
            or not is_loopback_host(request.client.host)
            or not is_loopback_host(request.url.hostname)
        ):
            raise HTTPException(status_code=403, detail="Local auth is restricted to loopback")
        try:
            current = service.get_principal(request.cookies.get(service.settings.cookie_name))
        except (LookupError, PermissionError):
            current = None
        if current is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return current

    def csrf(request: Request) -> None:
        service = _auth(app)
        if not service.require_csrf(
            request.cookies.get(service.settings.cookie_name),
            request.headers.get("X-CSRF-Token"),
        ):
            raise HTTPException(status_code=403, detail="CSRF token is invalid")

    def permitted_accounts(current: Principal, requested: list[str] | None) -> list[str]:
        allowed = list(DEFAULT_ACCOUNTS) if current.role == "owner" else [
            account for account in DEFAULT_ACCOUNTS if account in current.accounts
        ]
        if requested is None:
            return allowed
        if any(account not in allowed for account in requested):
            raise HTTPException(status_code=403, detail="Account access denied")
        return list(dict.fromkeys(requested))

    def permitted_target_accounts(current: Principal, requested: list[str] | None) -> list[str]:
        allowed = ["ALL", *DEFAULT_ACCOUNTS] if current.role == "owner" else [
            account for account in DEFAULT_ACCOUNTS if account in current.accounts
        ]
        if requested is None:
            return allowed
        if any(account not in allowed for account in requested):
            raise HTTPException(status_code=403, detail="Account access denied")
        return list(dict.fromkeys(requested))

    def owner(current: Principal = Depends(principal)) -> Principal:
        if current.role != "owner":
            raise HTTPException(status_code=403, detail="Owner role required")
        return current

    @app.get("/health")
    def health() -> dict[str, str]:
        with _engine(app).connect() as conn:
            conn.execute(select(1))
        return {"status": "ok"}

    @app.get("/auth/login")
    async def login() -> RedirectResponse:
        service = _auth(app)
        if service.settings.mode == "local":
            return RedirectResponse(_web_app_url(service), status_code=302)
        try:
            pending = await service.acreate_login_url()
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        response = RedirectResponse(pending.authorization_url, status_code=302)
        response.set_cookie(
            key=f"{service.settings.cookie_name}_oidc_state",
            value=pending.state,
            max_age=service.settings.state_ttl_seconds,
            path="/",
            secure=service.settings.cookie_secure,
            httponly=True,
            samesite="lax",
        )
        return response

    @app.get("/auth/callback")
    async def callback(request: Request, code: str, state: str) -> RedirectResponse:
        service = _auth(app)
        if service.settings.mode != "oidc":
            raise HTTPException(status_code=404, detail="OIDC is not enabled")
        browser_state = request.cookies.get(f"{service.settings.cookie_name}_oidc_state")
        if not browser_state or not secrets.compare_digest(browser_state, state):
            raise HTTPException(status_code=400, detail="OIDC browser state is invalid")
        try:
            _, tokens = await service.acomplete_oidc_callback(state=state, code=code)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response = RedirectResponse(_web_app_url(service), status_code=302)
        response.delete_cookie(f"{service.settings.cookie_name}_oidc_state", path="/")
        response.set_cookie(value=tokens.session_token, **service.cookie_options(tokens.expires_at))
        response.set_cookie(
            key=_csrf_cookie_name(service),
            value=tokens.csrf_token,
            max_age=service.settings.session_ttl_seconds,
            expires=tokens.expires_at,
            path="/",
            secure=service.settings.cookie_secure,
            httponly=False,
            samesite="lax",
        )
        return response

    @app.get("/auth/me")
    def me(current: Principal = Depends(principal)) -> dict[str, Any]:
        return {
            "email": current.email,
            "display_name": current.display_name,
            "role": current.role,
            "accounts": list(current.accounts),
            "auth_method": current.auth_method,
        }

    @app.post("/auth/logout")
    def logout(
        request: Request,
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> JSONResponse:
        del current
        service = _auth(app)
        service.revoke_session(request.cookies.get(service.settings.cookie_name))
        response = JSONResponse({"ok": True})
        response.delete_cookie(service.settings.cookie_name, path="/")
        response.delete_cookie(_csrf_cookie_name(service), path="/")
        return response

    @app.get("/api/v1/meta")
    def meta(current: Principal = Depends(principal)) -> dict[str, Any]:
        return {
            "accounts": permitted_accounts(current, None),
            "statuses": STATUSES,
            "max_upload_mb": MAX_UPLOAD_MB,
        }

    @app.get("/api/v1/overview")
    def overview_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        accounts = permitted_accounts(current, _list(account))
        items = _items(overview(_engine(app), accounts, start, end, _list(status)))
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/daily")
    def daily_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        accounts = permitted_accounts(current, _list(account))
        items = _items(daily_report(_engine(app), accounts, start, end, _list(status)))
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/monthly-kpi")
    def monthly_endpoint(
        month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        accounts = permitted_accounts(current, _list(account))
        df = monthly_kpi(_engine(app), accounts, start, end, _list(status))
        if month:
            df = df[pd.to_datetime(df["month"]).dt.strftime("%Y-%m") == month]
        items = _items(df)
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/targets")
    def targets_endpoint(
        month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
        account: list[str] | None = Query(None),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        accounts = permitted_target_accounts(current, _list(account))
        stmt = select(monthly_targets).where(monthly_targets.c.account.in_(accounts))
        if month:
            stmt = stmt.where(monthly_targets.c.month == _month_start(month))
        stmt = stmt.order_by(monthly_targets.c.month, monthly_targets.c.account)
        with _engine(app).connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        items = [
            {
                "account": row["account"],
                "month": row["month"].strftime("%Y-%m"),
                "target_commission": int(row["target_commission"]),
            }
            for row in rows
        ]
        return {"items": items, "count": len(items)}

    @app.put("/api/v1/targets/{account}/{month}")
    def update_target_endpoint(
        account: str,
        month: str,
        changes: TargetUpdate,
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        if current.role not in {"owner", "operator"}:
            raise HTTPException(status_code=403, detail="Target update requires operator or owner role")
        account = account.strip()
        if account not in permitted_target_accounts(current, [account]):
            raise HTTPException(status_code=403, detail="Account access denied")
        month_date = _month_start(month)
        values = {
            "account": account,
            "month": month_date,
            "target_commission": changes.target_commission,
        }
        with _engine(app).begin() as conn:
            if conn.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            stmt = insert(monthly_targets).values(**values).on_conflict_do_update(
                index_elements=["account", "month"],
                set_={"target_commission": changes.target_commission},
            )
            conn.execute(stmt)
        return {"account": account, "month": month, "target_commission": changes.target_commission}

    @app.get("/api/v1/orders")
    def orders_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        search: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        accounts = permitted_accounts(current, _list(account))
        df = orders(_engine(app), accounts, start, end, _list(status), search)
        total = len(df)
        page = df.iloc[offset : offset + limit]
        items = _items(page)
        return {"items": items, "count": len(items), "total": total, "limit": limit, "offset": offset}

    @app.post("/api/v1/imports")
    async def imports_endpoint(
        account: str = Form(...),
        file: UploadFile = File(...),
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        if current.role not in {"owner", "operator"}:
            raise HTTPException(status_code=403, detail="Import requires operator or owner role")
        account = account.strip()
        if not account:
            raise HTTPException(status_code=422, detail="account is required")
        if account not in DEFAULT_ACCOUNTS:
            raise HTTPException(status_code=422, detail="account is not allowed")
        permitted_accounts(current, [account])
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise HTTPException(status_code=415, detail="only .xlsx files are supported")
        data = await _read_upload(file)
        try:
            rows = read_xlsx(BytesIO(data), account)
            result = import_rows(
                _engine(app),
                filename=file.filename or "upload.xlsx",
                file_bytes=data,
                account=account,
                rows=rows,
                uploaded_by_label=current.display_name or current.email,
                auth_method=current.auth_method,
                auth_subject=current.auth_subject,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "batch_id": result.get("batch_id"),
            "duplicate": bool(result.get("duplicate")),
            "inserted": int(result.get("inserted", 0)),
            "updated": int(result.get("updated", 0)),
            "unchanged": int(result.get("unchanged", 0)),
            "rejected": int(result.get("rejected", 0)),
            "rejected_rows": result.get("rejected_rows", []),
        }

    @app.get("/api/v1/imports")
    def imports_history_endpoint(
        account: list[str] | None = Query(None),
        limit: int = Query(10, ge=1, le=100),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        accounts = permitted_accounts(current, _list(account))
        stmt = (
            select(
                import_batches.c.id,
                import_batches.c.filename,
                import_batches.c.account,
                import_batches.c.uploaded_by_label,
                import_batches.c.inserted,
                import_batches.c.updated,
                import_batches.c.unchanged,
                import_batches.c.rejected,
                import_batches.c.created_at,
            )
            .where(import_batches.c.account.in_(accounts))
            .order_by(import_batches.c.created_at.desc(), import_batches.c.id.desc())
            .limit(limit)
        )
        with _engine(app).connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        items = [{key: _clean(value) for key, value in row.items()} for row in rows]
        return {"items": items, "count": len(items), "limit": limit}

    @app.post("/api/v1/admin/reset-data")
    def reset_data_endpoint(
        request: ResetDataRequest,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, Any]:
        if request.confirmation != RESET_CONFIRMATION_PHRASE:
            raise HTTPException(status_code=422, detail=f"confirmation must be {RESET_CONFIRMATION_PHRASE!r}")
        try:
            return reset_sqlite_business_data(_engine(app))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/v1/admin/backups")
    def list_backups_endpoint(_: Principal = Depends(owner)) -> dict[str, Any]:
        try:
            items = list_sqlite_backups(_engine(app))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/admin/backups/{backup_id:path}/preview")
    def preview_backup_endpoint(backup_id: str, _: Principal = Depends(owner)) -> dict[str, Any]:
        try:
            return preview_sqlite_backup(_engine(app), backup_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/admin/backups/restore")
    def restore_backup_endpoint(
        request: RestoreBackupRequest,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, Any]:
        if request.confirmation != RESTORE_CONFIRMATION_PHRASE:
            raise HTTPException(status_code=422, detail=f"confirmation must be {RESTORE_CONFIRMATION_PHRASE!r}")
        try:
            return restore_sqlite_business_backup(_engine(app), request.backup_id, request.confirmation)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/v1/admin/update")
    def check_update_endpoint(_: Principal = Depends(owner)) -> dict[str, Any]:
        if _auth(app).settings.mode != "local":
            raise HTTPException(status_code=409, detail="Automatic updates are only available in local mode.")
        try:
            result = check_for_update()
        except UpdateError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        result["automatic_install_supported"] = _automatic_update_supported(app)
        return result

    @app.post("/api/v1/admin/update/install")
    def install_update_endpoint(
        request: InstallUpdateRequest,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, Any]:
        if request.confirmation != INSTALL_CONFIRMATION_PHRASE:
            raise HTTPException(status_code=422, detail=f"confirmation must be {INSTALL_CONFIRMATION_PHRASE!r}")
        if _auth(app).settings.mode != "local":
            raise HTTPException(status_code=409, detail="Automatic updates are only available in local mode.")
        shutdown = getattr(app.state, "update_shutdown", None)
        if not _automatic_update_supported(app):
            raise HTTPException(status_code=409, detail="Automatic installation requires the installed Windows app.")
        with app.state.update_lock:
            if app.state.update_scheduled:
                raise HTTPException(status_code=409, detail="An update is already scheduled.")
            try:
                data_dir = sqlite_file_path(_engine(app)).parent
                downloaded = download_latest_update(data_dir)
                schedule_installer(
                    Path(downloaded["installer_path"]),
                    downloaded["sha256"],
                    data_dir / "updater.log",
                    shutdown,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except UpdateError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            app.state.update_scheduled = True
        return {
            "status": "scheduled",
            "version": downloaded["version"],
            "sha256": downloaded["sha256"],
            "release_url": downloaded["release_url"],
        }

    @app.get("/api/v1/admin/users")
    def users(_: Principal = Depends(owner)) -> dict[str, Any]:
        items = _auth(app).list_users()
        return {"items": items, "count": len(items)}

    @app.patch("/api/v1/admin/users/{user_id}")
    def update_user_endpoint(
        user_id: int,
        changes: UserUpdate,
        _: None = Depends(csrf),
        current: Principal = Depends(owner),
    ) -> dict[str, Any]:
        if current.user_id == user_id and (changes.active is False or changes.role in {"operator", "viewer"}):
            raise HTTPException(status_code=409, detail="Owner cannot remove their own active owner access")
        accounts = None if changes.accounts is None else list(dict.fromkeys(changes.accounts))
        try:
            updated = _auth(app).update_user(
                user_id,
                role=changes.role,
                accounts=accounts,
                active=changes.active,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "id": updated.user_id,
            "email": updated.email,
            "display_name": updated.display_name,
            "role": updated.role,
            "accounts": list(updated.accounts),
        }

    static_dir = os.getenv("WEB_STATIC_DIR")
    if static_dir and os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")

    return app


app = create_app()
