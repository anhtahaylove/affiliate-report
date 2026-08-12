from __future__ import annotations

import math
import os
import secrets
import sys
import threading
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Literal

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
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from .accounts import (
    ACCOUNT_CODE_RE,
    can_hard_delete_accounts,
    create_account,
    delete_account,
    delete_account_preview,
    list_accounts,
    update_account,
)
from .auth import AuthService, AuthSettings, Principal, is_loopback_host
from .db import accounts as account_registry
from .db import get_engine, import_batches, import_rows, init_db, monthly_targets
from .imports import order_line_history, undo_import, undo_preview
from .parser import read_xlsx
from .reports import (
    ORDER_EXPORT_COLUMNS,
    analytics,
    count_orders,
    daily_report,
    collapse_kpi_to_scope,
    monthly_kpi,
    orders,
    overview,
    sheets_output,
)
from .static_export import StaticExportFiles, service_worker_response
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
    public_update_issue,
    read_update_status,
    schedule_installer,
    write_update_status,
)
from .version import APP_VERSION

MAX_UPLOAD_MB = 20
STATUSES = ["settled", "ineligible", "pending", "unknown"]


class UserUpdate(BaseModel):
    role: Literal["owner", "operator", "viewer"] | None = None
    accounts: list[str] | None = None
    active: bool | None = None

class PreferencesPatch(BaseModel):
    theme: Literal["system", "light", "dark"] | None = None
    sidebar_collapsed: bool | None = None
    dashboard_layout: dict[str, Any] | None = None


class SavedViewCreate(BaseModel):
    route: Literal["dashboard", "analytics", "orders"]
    name: str = Field(min_length=1, max_length=64)
    filters: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class SavedViewPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    filters: dict[str, Any] | None = None
    is_default: bool | None = None


DASHBOARD_WIDGETS = (
    "today_pulse",
    "target_progress",
    "action_alerts",
    "trend",
    "account_contribution",
    "settlement",
    "data_freshness",
    "recent_imports",
)
DEFAULT_DASHBOARD_LAYOUT = {"schema": 1, "order": list(DASHBOARD_WIDGETS), "hidden": []}
DEFAULT_UI_PREFERENCES = {
    "theme": "system",
    "sidebar_collapsed": False,
    "dashboard_layout": DEFAULT_DASHBOARD_LAYOUT,
}
COMMON_VIEW_FILTERS = {"schema", "account", "status", "start", "end", "month"}
VIEW_FILTERS = {
    "dashboard": COMMON_VIEW_FILTERS,
    "analytics": COMMON_VIEW_FILTERS | {"group_by", "top"},
    "orders": COMMON_VIEW_FILTERS | {"search", "sort", "direction", "size"},
}
ORDER_SORT_FIELDS = {
    "account", "order_id", "sku_id", "product_name", "status", "order_date",
    "units_sold", "gmv", "estimated_commission",
}


def _validate_dashboard_layout(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"schema", "order", "hidden"} or value.get("schema") != 1:
        raise HTTPException(status_code=422, detail="dashboard_layout không đúng schema 1.")
    order = value.get("order")
    hidden = value.get("hidden")
    if not isinstance(order, list) or not isinstance(hidden, list):
        raise HTTPException(status_code=422, detail="dashboard_layout order/hidden phải là danh sách.")
    if len(order) != len(set(order)) or set(order) != set(DASHBOARD_WIDGETS):
        raise HTTPException(status_code=422, detail="dashboard_layout phải chứa đúng danh sách widget hỗ trợ.")
    if len(hidden) != len(set(hidden)) or not set(hidden).issubset(DASHBOARD_WIDGETS):
        raise HTTPException(status_code=422, detail="dashboard_layout hidden chứa widget không hợp lệ.")
    return {"schema": 1, "order": list(order), "hidden": list(hidden)}


def _valid_date_filter(value: Any, pattern: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, pattern)
        return True
    except ValueError:
        return False


def _sanitize_view_filters(route: str, values: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    allowed = VIEW_FILTERS[route]
    unknown = set(values) - allowed
    if strict and unknown:
        raise HTTPException(status_code=422, detail=f"Bộ lọc không hỗ trợ: {', '.join(sorted(unknown))}")
    output: dict[str, Any] = {"schema": 1}
    def valid_account(value: Any) -> bool:
        items = value if isinstance(value, list) else [value]
        return (
            1 <= len(items) <= 100
            and all(isinstance(item, str) and item != "ALL" and ACCOUNT_CODE_RE.fullmatch(item) for item in items)
        )

    def valid_status(value: Any) -> bool:
        items = value if isinstance(value, list) else [value]
        return (
            1 <= len(items) <= len(STATUSES)
            and all(isinstance(item, str) for item in items)
            and len(items) == len(set(items))
            and set(items).issubset(STATUSES)
        )

    validators: dict[str, Callable[[Any], bool]] = {
        "schema": lambda value: value == 1,
        "account": valid_account,
        "status": valid_status,
        "start": lambda value: _valid_date_filter(value, "%Y-%m-%d"),
        "end": lambda value: _valid_date_filter(value, "%Y-%m-%d"),
        "month": lambda value: _valid_date_filter(value, "%Y-%m"),
        "search": lambda value: isinstance(value, str) and len(value) <= 256,
        "sort": lambda value: isinstance(value, str) and value in ORDER_SORT_FIELDS,
        "direction": lambda value: value in {"asc", "desc"},
        "size": lambda value: isinstance(value, int) and not isinstance(value, bool) and value in {50, 100, 200},
        "group_by": lambda value: value in {"day", "week", "month"},
        "top": lambda value: isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 100,
    }
    for key, value in values.items():
        if key not in allowed:
            continue
        if not validators[key](value):
            if strict:
                raise HTTPException(status_code=422, detail=f"Giá trị bộ lọc {key!r} không hợp lệ.")
            continue
        if key != "schema":
            output[key] = value
    return output


class TargetUpdate(BaseModel):
    # Nhận cả tên cũ vì tab đang mở lúc app cập nhật vẫn chạy bản JS trước đó vài phút.
    daily_target_commission: int = Field(
        ge=0,
        le=1_000_000_000_000,
        validation_alias=AliasChoices("daily_target_commission", "target_commission"),
    )


class ResetDataRequest(BaseModel):
    confirmation: str


class RestoreBackupRequest(BaseModel):
    backup_id: str
    confirmation: str


class InstallUpdateRequest(BaseModel):
    confirmation: str


class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    display_order: int | None = Field(default=None, ge=0, le=1_000_000)


class AccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    display_order: int | None = Field(default=None, ge=0, le=1_000_000)
    active: bool | None = None


class AccountDeleteRequest(BaseModel):
    confirmation: str


class UndoImportRequest(BaseModel):
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


def _clean_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_nested(item) for item in value]
    return _clean(value)


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


def _previous_month(month: date) -> date:
    return date(month.year - 1, 12, 1) if month.month == 1 else date(month.year, month.month - 1, 1)


def _engine(app: FastAPI) -> Engine:
    return app.state.engine


def _account_items(engine: Engine, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    stmt = select(account_registry)
    if not include_inactive:
        stmt = stmt.where(account_registry.c.active.is_(True))
    stmt = stmt.order_by(account_registry.c.display_order, account_registry.c.code)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [{key: _clean(value) for key, value in row.items()} for row in rows]


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


def _desktop_shutdown_supported(app: FastAPI) -> bool:
    return (
        _auth(app).settings.mode == "local"
        and _automatic_update_supported(app)
        and bool(os.getenv("DESKTOP_CONTROL_TOKEN"))
    )


def _capability(available: bool, reason: str | None = None) -> dict[str, Any]:
    return {"available": available, "reason": None if available else reason}


def _runtime_capabilities(app: FastAPI) -> dict[str, Any]:
    engine = _engine(app)
    auth_mode = _auth(app).settings.mode
    try:
        sqlite_file_path(engine)
        data_admin = _capability(True)
    except ValueError as exc:
        if engine.dialect.name == "postgresql":
            reason = (
                "PostgreSQL dùng chung được sao lưu và khôi phục ở tầng hạ tầng; "
                "Reset Data và backup cục bộ đã tắt để tránh thao tác phá hủy ngoài phạm vi một máy."
            )
        else:
            reason = str(exc)
        data_admin = _capability(False, reason)

    update_check_available = auth_mode == "local" and data_admin["available"]
    if auth_mode != "local":
        update_reason = (
            "Bản triển khai OIDC dùng chung được cập nhật tại máy chủ; "
            "trình cập nhật Windows cục bộ không chạy trong môi trường này."
        )
    else:
        update_reason = (
            "Trình cập nhật Windows cần database SQLite cục bộ để lưu trạng thái; "
            "môi trường database dùng chung được cập nhật tại máy chủ."
        )
    install_available = update_check_available and _automatic_update_supported(app)
    install_reason = (
        update_reason
        if not update_check_available
        else "Cài tự động chỉ khả dụng trong bản Windows đã cài đặt."
    )
    return {
        "database_backend": engine.dialect.name,
        "auth_mode": auth_mode,
        "data_admin": data_admin,
        "update_check": _capability(update_check_available, update_reason),
        "update_install": _capability(install_available, install_reason),
    }


def _identity_policy(app: FastAPI) -> dict[str, Any]:
    mode = _auth(app).settings.mode
    return {
        "mode": mode,
        "oidc_allowlist_enforced": mode == "oidc",
        "enforcement": "login_and_active_sessions" if mode == "oidc" else "local_owner",
    }


def _require_capability(capability: dict[str, Any]) -> None:
    if not capability["available"]:
        raise HTTPException(status_code=409, detail=capability["reason"])


def _start_update_worker(target: Callable[[], None]) -> None:
    threading.Thread(target=target, name="app-updater", daemon=True).start()


async def _read_upload(file: UploadFile) -> bytes:
    limit = MAX_UPLOAD_MB * 1024 * 1024
    data = bytearray()
    while chunk := await file.read(min(1024 * 1024, limit + 1 - len(data))):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB")
    return bytes(data)


def _xlsx_response(df: pd.DataFrame, filename: str, sheet_name: str) -> StreamingResponse:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        worksheet = writer.book[sheet_name]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token", "X-Desktop-Control-Token"],
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
        active = [item["code"] for item in _account_items(_engine(app))]
        allowed = active if current.role == "owner" else [account for account in active if account in current.accounts]
        if requested is None:
            return allowed
        requested = list(dict.fromkeys(account.strip().upper() for account in requested))
        if "ALL" in requested:
            if requested != ["ALL"]:
                raise HTTPException(status_code=422, detail="ALL must be the only account filter")
            return allowed
        if any(account not in allowed for account in requested):
            raise HTTPException(status_code=403, detail="Account access denied")
        return requested

    def permitted_view_filters(
        current: Principal,
        route: str,
        values: dict[str, Any],
        *,
        strict: bool,
    ) -> dict[str, Any]:
        filters = _sanitize_view_filters(route, values, strict=strict)
        requested = filters.get("account")
        if not requested:
            return filters
        allowed = set(permitted_accounts(current, None))
        visible = [account for account in requested if account in allowed]
        if strict and len(visible) != len(requested):
            raise HTTPException(status_code=403, detail="Account access denied")
        if visible:
            filters["account"] = visible
        else:
            filters.pop("account", None)
        return filters

    def permitted_target_accounts(current: Principal, requested: list[str] | None) -> list[str]:
        active = [item["code"] for item in _account_items(_engine(app))]
        allowed = ["ALL", *active] if current.role == "owner" else [account for account in active if account in current.accounts]
        if requested is None:
            return allowed
        requested = [account.strip().upper() for account in requested]
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
        desktop_app = current.role == "owner" and _desktop_shutdown_supported(app)
        return {
            "email": current.email,
            "display_name": current.display_name,
            "role": current.role,
            "accounts": list(current.accounts),
            "auth_method": current.auth_method,
            "desktop_app": desktop_app,
            "desktop_control_token": os.getenv("DESKTOP_CONTROL_TOKEN") if desktop_app else None,
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
        accounts = permitted_accounts(current, None)
        allowed = set(accounts)
        return {
            "accounts": accounts,
            "account_items": [item for item in _account_items(_engine(app)) if item["code"] in allowed],
            "statuses": STATUSES,
            "max_upload_mb": MAX_UPLOAD_MB,
            # Hiện ngay ở thanh bên: trước đây chỉ owner xem được, nằm sâu trong Cài đặt >
            # Cập nhật, nên người báo lỗi thường không biết mình đang chạy bản nào.
            "app_version": APP_VERSION,
            "capabilities": _runtime_capabilities(app),
            "identity_policy": _identity_policy(app),
        }

    @app.get("/api/v1/accounts")
    def accounts_endpoint(_: Principal = Depends(owner)) -> dict[str, Any]:
        items = [_clean_nested(item) for item in list_accounts(_engine(app), include_inactive=True)]
        return {"items": items, "count": len(items), "hard_delete_supported": can_hard_delete_accounts(_engine(app))}

    @app.post("/api/v1/accounts", status_code=201)
    def create_account_endpoint(
        changes: AccountCreate,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, Any]:
        try:
            return _clean_nested(create_account(
                _engine(app),
                changes.code,
                display_name=changes.display_name,
                display_order=changes.display_order,
            ))
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Account code đã tồn tại.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/api/v1/accounts/{code}")
    def update_account_endpoint(
        code: str,
        changes: AccountUpdate,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, Any]:
        try:
            return _clean_nested(update_account(
                _engine(app),
                code,
                display_name=changes.display_name,
                display_order=changes.display_order,
                active=changes.active,
            ))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/accounts/{code}/delete-preview")
    def delete_account_preview_endpoint(code: str, _: Principal = Depends(owner)) -> dict[str, Any]:
        try:
            result = delete_account_preview(_engine(app), code)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not result["exists"]:
            raise HTTPException(status_code=404, detail="Không tìm thấy account.")
        result["action"] = "hard_delete" if result["can_hard_delete"] else "archive"
        return result

    @app.delete("/api/v1/accounts/{code}")
    def delete_account_endpoint(
        code: str,
        request: AccountDeleteRequest,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, Any]:
        normalized = code.strip().upper()
        expected = f"XOA {normalized}"
        if request.confirmation != expected:
            raise HTTPException(status_code=422, detail=f"confirmation must be {expected!r}")
        try:
            engine = _engine(app)
            return _clean_nested(delete_account(engine, normalized, hard=can_hard_delete_accounts(engine)))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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
        # Một dòng cho mỗi tài khoản, phủ đúng phạm vi ngày đang xem — xem collapse_kpi_to_scope.
        items = _items(collapse_kpi_to_scope(df))
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/analytics")
    def analytics_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        group_by: Literal["day", "week", "month"] = "day",
        top: int = Query(20, ge=1, le=100),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        if start and end and start > end:
            raise HTTPException(status_code=422, detail="start must not be after end")
        accounts = permitted_accounts(current, _list(account))
        result = analytics(
            _engine(app),
            accounts=accounts,
            start=start,
            end=end,
            statuses=_list(status),
            group_by=group_by,
            top=top,
        )
        return _clean_nested(result)

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
                "daily_target_commission": int(row["daily_target_commission"]),
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
        account = account.strip().upper()
        if account not in permitted_target_accounts(current, [account]):
            raise HTTPException(status_code=403, detail="Account access denied")
        month_date = _month_start(month)
        values = {
            "account": account,
            "month": month_date,
            "daily_target_commission": changes.daily_target_commission,
        }
        with _engine(app).begin() as conn:
            if conn.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            stmt = insert(monthly_targets).values(**values).on_conflict_do_update(
                index_elements=["account", "month"],
                set_={"daily_target_commission": changes.daily_target_commission},
            )
            conn.execute(stmt)
        return {"account": account, "month": month, "daily_target_commission": changes.daily_target_commission}

    @app.post("/api/v1/targets/{month}/copy-previous")
    def copy_previous_targets_endpoint(
        month: str,
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        """Chép KPI tháng trước sang tháng này cho các tài khoản chưa đặt.

        Sang tháng mới thì KPI thường giữ nguyên, nhưng phải gõ lại từng tài khoản một.
        Cố ý KHÔNG đè lên tài khoản đã có KPI cho tháng đích: chép đè sẽ xoá mất con số vừa
        chỉnh mà không hỏi, còn bỏ qua thì cùng lắm là bấm thừa một lần.
        """
        if current.role not in {"owner", "operator"}:
            raise HTTPException(status_code=403, detail="Target update requires operator or owner role")
        target_month = _month_start(month)
        source_month = _previous_month(target_month)
        allowed = set(permitted_target_accounts(current, None))
        with _engine(app).begin() as conn:
            existing = {
                row.account
                for row in conn.execute(select(monthly_targets.c.account).where(monthly_targets.c.month == target_month))
            }
            source = [
                row for row in conn.execute(
                    select(monthly_targets.c.account, monthly_targets.c.daily_target_commission)
                    .where(monthly_targets.c.month == source_month)
                    .order_by(monthly_targets.c.account)
                )
                if row.account in allowed
            ]
            copied = [row for row in source if row.account not in existing]
            if copied:
                conn.execute(
                    monthly_targets.insert(),
                    [
                        {"account": row.account, "month": target_month, "daily_target_commission": int(row.daily_target_commission)}
                        for row in copied
                    ],
                )
        return {
            "month": month,
            "from_month": source_month.strftime("%Y-%m"),
            "copied": [{"account": row.account, "daily_target_commission": int(row.daily_target_commission)} for row in copied],
            "kept": sorted(row.account for row in source if row.account in existing),
        }

    @app.get("/api/v1/orders")
    def orders_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        search: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        sort: str | None = Query(None),
        direction: Literal["asc", "desc"] = "desc",
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        accounts = permitted_accounts(current, _list(account))
        statuses = _list(status)
        engine = _engine(app)
        total = count_orders(engine, accounts, start, end, statuses, search)
        try:
            page = orders(engine, accounts, start, end, statuses, search, limit=limit, offset=offset, sort=sort, direction=direction)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        items = _items(page)
        return {"items": items, "count": len(items), "total": total, "limit": limit, "offset": offset}

    @app.get("/api/v1/orders/export.xlsx")
    def orders_export_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        search: str | None = None,
        current: Principal = Depends(principal),
    ) -> StreamingResponse:
        accounts = permitted_accounts(current, _list(account))
        df = orders(_engine(app), accounts, start, end, _list(status), search)
        return _xlsx_response(df[ORDER_EXPORT_COLUMNS], "tiktok-affiliate-orders.xlsx", "Orders")

    @app.get("/api/v1/reports/daily.xlsx")
    def daily_export_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        current: Principal = Depends(principal),
    ) -> StreamingResponse:
        accounts = permitted_accounts(current, _list(account))
        df = sheets_output(_engine(app), accounts, start, end, _list(status))
        return _xlsx_response(df, "tiktok-affiliate-daily-report.xlsx", "Daily report")

    @app.post("/api/v1/imports")
    async def imports_endpoint(
        account: str = Form(...),
        file: UploadFile = File(...),
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        if current.role not in {"owner", "operator"}:
            raise HTTPException(status_code=403, detail="Import requires operator or owner role")
        account = account.strip().upper()
        if not account:
            raise HTTPException(status_code=422, detail="account is required")
        if account == "ALL":
            raise HTTPException(status_code=422, detail="ALL is a virtual report scope and cannot receive imports")
        permitted_accounts(current, [account])
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise HTTPException(status_code=415, detail="only .xlsx files are supported")
        data = await _read_upload(file)

        # Parse + ghi DB là công việc đồng bộ nặng; chạy trong threadpool để event loop
        # vẫn phục vụ được /health, tray và các tab khác suốt lần nhập.
        def ingest() -> dict[str, Any]:
            return import_rows(
                _engine(app),
                filename=file.filename or "upload.xlsx",
                file_bytes=data,
                account=account,
                rows=read_xlsx(BytesIO(data), account),
                uploaded_by_label=current.display_name or current.email,
                auth_method=current.auth_method,
                auth_subject=current.auth_subject,
            )

        try:
            result = await run_in_threadpool(ingest)
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

    def writable_batch(current: Principal, batch_id: int) -> dict[str, Any]:
        if current.role not in {"owner", "operator"}:
            raise HTTPException(status_code=403, detail="Hoàn tác lần nhập cần quyền vận hành hoặc chủ sở hữu")
        try:
            preview = undo_preview(_engine(app), batch_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        permitted_accounts(current, [str(preview["account"])])
        return preview

    @app.get("/api/v1/imports/{batch_id}/undo-preview")
    def undo_preview_endpoint(batch_id: int, current: Principal = Depends(principal)) -> dict[str, Any]:
        return _clean_nested(writable_batch(current, batch_id))

    @app.delete("/api/v1/imports/{batch_id}")
    def undo_import_endpoint(
        batch_id: int,
        request: UndoImportRequest,
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        writable_batch(current, batch_id)
        try:
            return _clean_nested(undo_import(_engine(app), batch_id, request.confirmation))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/orders/{business_key}/versions")
    def order_versions_endpoint(business_key: str, current: Principal = Depends(principal)) -> dict[str, Any]:
        items = order_line_history(_engine(app), business_key)
        if not items:
            raise HTTPException(status_code=404, detail="Không tìm thấy dòng đơn.")
        permitted_accounts(current, [str(items[0]["account"])])
        return {"items": [_clean_nested(item) for item in items], "count": len(items)}

    @app.post("/api/v1/admin/reset-data")
    def reset_data_endpoint(
        request: ResetDataRequest,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, Any]:
        _require_capability(_runtime_capabilities(app)["data_admin"])
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
        _require_capability(_runtime_capabilities(app)["data_admin"])
        try:
            items = list_sqlite_backups(_engine(app))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/admin/backups/{backup_id:path}/preview")
    def preview_backup_endpoint(backup_id: str, _: Principal = Depends(owner)) -> dict[str, Any]:
        _require_capability(_runtime_capabilities(app)["data_admin"])
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
        _require_capability(_runtime_capabilities(app)["data_admin"])
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
        _require_capability(_runtime_capabilities(app)["update_check"])
        try:
            result = check_for_update()
        except UpdateError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        result["automatic_install_supported"] = _automatic_update_supported(app)
        return result

    @app.get("/api/v1/admin/update/progress")
    def update_progress_endpoint(_: Principal = Depends(owner)) -> dict[str, Any]:
        _require_capability(_runtime_capabilities(app)["update_check"])
        try:
            data_dir = sqlite_file_path(_engine(app)).parent
            result = read_update_status(data_dir / "update-status.json")
        except (ValueError, UpdateError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        downloaded = int(result.get("bytes_downloaded") or 0)
        total = int(result.get("bytes_total") or 0)
        public_error, error_action = public_update_issue(str(result.get("phase") or ""), result.get("error"))
        result["error"] = public_error
        result["error_action"] = error_action
        result["current_version"] = APP_VERSION
        result["percent"] = round(downloaded * 100 / total, 1) if total > 0 else None
        return result

    @app.post("/api/v1/admin/update/install")
    def install_update_endpoint(
        request: InstallUpdateRequest,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, Any]:
        if request.confirmation != INSTALL_CONFIRMATION_PHRASE:
            raise HTTPException(status_code=422, detail=f"confirmation must be {INSTALL_CONFIRMATION_PHRASE!r}")
        _require_capability(_runtime_capabilities(app)["update_install"])
        shutdown = getattr(app.state, "update_shutdown", None)
        try:
            data_dir = sqlite_file_path(_engine(app)).parent
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        status_path = data_dir / "update-status.json"
        with app.state.update_lock:
            if app.state.update_scheduled:
                raise HTTPException(status_code=409, detail="An update is already scheduled.")
            try:
                latest = check_for_update()
                if not latest["available"]:
                    raise ValueError("Ứng dụng đang ở phiên bản mới nhất.")
                version = str(latest["latest_version"])
                write_update_status(
                    status_path,
                    phase="downloading",
                    target_version=version,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except UpdateError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            app.state.update_scheduled = True
            release_url = str(latest["release_url"])

            def run_update() -> None:
                try:
                    def report_download(downloaded_bytes: int, total_bytes: int) -> None:
                        write_update_status(
                            status_path,
                            phase="downloading",
                            target_version=version,
                            bytes_downloaded=downloaded_bytes,
                            bytes_total=total_bytes,
                        )

                    downloaded = download_latest_update(data_dir, progress_callback=report_download)
                    downloaded_version = str(downloaded["version"])
                    installer_path = Path(downloaded["installer_path"])
                    write_update_status(
                        status_path,
                        phase="verifying",
                        target_version=downloaded_version,
                        bytes_downloaded=installer_path.stat().st_size,
                        bytes_total=installer_path.stat().st_size,
                    )
                    schedule_installer(
                        installer_path,
                        downloaded["sha256"],
                        data_dir / "updater.log",
                        shutdown,
                        status_path=status_path,
                        target_version=downloaded_version,
                        installer_size=installer_path.stat().st_size,
                        instance_state_path=data_dir / "instance.json",
                    )
                except Exception as exc:
                    try:
                        write_update_status(
                            status_path,
                            phase="failed",
                            target_version=version,
                            error=str(exc),
                        )
                    except Exception as status_exc:
                        print(f"Update failed: {exc}; status write failed: {status_exc}")
                    with app.state.update_lock:
                        app.state.update_scheduled = False

        try:
            _start_update_worker(run_update)
        except RuntimeError as exc:
            with app.state.update_lock:
                app.state.update_scheduled = False
            write_update_status(
                status_path,
                phase="failed",
                target_version=version,
                error="Không thể khởi chạy tiến trình cập nhật.",
            )
            raise HTTPException(status_code=500, detail="Không thể khởi chạy tiến trình cập nhật.") from exc
        return {
            "status": "started",
            "version": version,
            "release_url": release_url,
        }

    @app.post("/api/v1/admin/shutdown")
    def shutdown_endpoint(
        request: Request,
        _: None = Depends(csrf),
        __: Principal = Depends(owner),
    ) -> dict[str, str]:
        if not _desktop_shutdown_supported(app):
            raise HTTPException(status_code=409, detail="Shutdown is only available in the installed local Windows app.")
        expected = os.getenv("DESKTOP_CONTROL_TOKEN", "")
        supplied = request.headers.get("X-Desktop-Control-Token", "")
        if not supplied or not secrets.compare_digest(supplied, expected):
            raise HTTPException(status_code=403, detail="Desktop control token is invalid.")
        shutdown = getattr(app.state, "update_shutdown", None)
        timer = threading.Timer(0.15, shutdown)
        timer.daemon = True
        timer.start()
        return {"status": "shutting_down"}

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
        accounts = None if changes.accounts is None else list(dict.fromkeys(account.strip().upper() for account in changes.accounts))
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
            "active": updated.active,
            "accounts": list(updated.accounts),
        }

    @app.get("/api/v1/ui/preferences")
    def get_preferences(current: Principal = Depends(principal)) -> dict[str, Any]:
        stored = _auth(app).get_preferences(current) or {}
        theme = stored.get("theme")
        if theme not in {"system", "light", "dark"}:
            theme = DEFAULT_UI_PREFERENCES["theme"]
        try:
            dashboard_layout = _validate_dashboard_layout(
                stored.get("dashboard_layout", DEFAULT_DASHBOARD_LAYOUT)
            )
        except HTTPException:
            dashboard_layout = _validate_dashboard_layout(DEFAULT_DASHBOARD_LAYOUT)
        return {
            "theme": theme,
            "sidebar_collapsed": stored.get("sidebar_collapsed", DEFAULT_UI_PREFERENCES["sidebar_collapsed"]),
            "dashboard_layout": dashboard_layout,
            "updated_at": stored.get("updated_at"),
        }

    @app.patch("/api/v1/ui/preferences")
    def patch_preferences(
        changes: PreferencesPatch,
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        current_values = get_preferences(current)
        values = current_values | changes.model_dump(exclude_none=True)
        values["dashboard_layout"] = _validate_dashboard_layout(values["dashboard_layout"])
        _auth(app).save_preferences(current, values)
        return get_preferences(current)

    @app.get("/api/v1/ui/saved-views")
    def get_saved_views(
        route: Literal["dashboard", "analytics", "orders"],
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        items = _auth(app).list_views(current, route)
        for item in items:
            item["filters"] = permitted_view_filters(
                current,
                route,
                item.get("filters") or {},
                strict=False,
            )
        return {"items": items, "count": len(items)}

    @app.post("/api/v1/ui/saved-views")
    def post_saved_view(
        request: SavedViewCreate,
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        name = request.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Tên chế độ xem là bắt buộc.")
        filters = permitted_view_filters(current, request.route, request.filters, strict=True)
        try:
            return _auth(app).create_view(current, request.route, name, filters, request.is_default)
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Tên chế độ xem đã tồn tại.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.patch("/api/v1/ui/saved-views/{view_id}")
    def patch_saved_view(
        view_id: int,
        request: SavedViewPatch,
        _: None = Depends(csrf),
        current: Principal = Depends(principal),
    ) -> dict[str, Any]:
        existing = _auth(app).get_view(current, view_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy chế độ xem.")
        name = request.name.strip() if request.name is not None else None
        if request.name is not None and not name:
            raise HTTPException(status_code=422, detail="Tên chế độ xem là bắt buộc.")
        filters = (
            permitted_view_filters(current, existing["route"], request.filters, strict=True)
            if request.filters is not None
            else None
        )
        try:
            updated = _auth(app).update_view(
                current,
                view_id,
                name=name,
                filters=filters,
                is_default=request.is_default,
            )
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Tên chế độ xem đã tồn tại.") from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy chế độ xem.")
        return updated

    @app.delete("/api/v1/ui/saved-views/{view_id}")
    def remove_saved_view(view_id: int, _: None = Depends(csrf), current: Principal = Depends(principal)) -> dict[str, bool]:
        if not _auth(app).delete_view(current, view_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy chế độ xem.")
        return {"deleted": True}

    static_dir = os.getenv("WEB_STATIC_DIR")
    if static_dir and os.path.isdir(static_dir):
        if os.path.isfile(os.path.join(static_dir, "sw.js")):
            @app.get("/sw.js", include_in_schema=False)
            def versioned_service_worker():
                return service_worker_response(static_dir, APP_VERSION)

        app.mount("/", StaticExportFiles(directory=static_dir, html=True), name="web")

    return app


app = create_app()
