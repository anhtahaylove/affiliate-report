from __future__ import annotations

import math
import os
from datetime import date, datetime
from io import BytesIO
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.engine import Engine

from .db import get_engine, import_rows, init_db
from .parser import DEFAULT_ACCOUNTS, read_xlsx
from .reports import daily_report, monthly_kpi, orders, overview

MAX_UPLOAD_MB = 20
STATUSES = ["settled", "ineligible", "pending", "unknown"]


def _cors_origins() -> list[str]:
    raw = os.getenv("API_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8501,http://127.0.0.1:8501")
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


def _engine(app: FastAPI) -> Engine:
    return app.state.engine


async def _read_upload(file: UploadFile) -> bytes:
    limit = MAX_UPLOAD_MB * 1024 * 1024
    data = bytearray()
    while chunk := await file.read(min(1024 * 1024, limit + 1 - len(data))):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB")
    return bytes(data)


def create_app(engine: Engine | None = None) -> FastAPI:
    app = FastAPI(
        title="TikTok Affiliate Report API",
        description="Local-only Phase-2 API foundation; runtime auth is intentionally out of scope before OIDC.",
        version="0.2.0",
    )
    app.state.engine = engine or get_engine()
    init_db(app.state.engine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        with _engine(app).connect() as conn:
            conn.execute(select(1))
        return {"status": "ok"}

    @app.get("/api/v1/meta")
    def meta() -> dict[str, Any]:
        return {"accounts": DEFAULT_ACCOUNTS, "statuses": STATUSES, "max_upload_mb": MAX_UPLOAD_MB}

    @app.get("/api/v1/overview")
    def overview_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        items = _items(overview(_engine(app), _list(account), start, end, _list(status)))
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/daily")
    def daily_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        items = _items(daily_report(_engine(app), _list(account), start, end, _list(status)))
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/monthly-kpi")
    def monthly_endpoint(
        month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        df = monthly_kpi(_engine(app), _list(account), start, end, _list(status))
        if month:
            df = df[pd.to_datetime(df["month"]).dt.strftime("%Y-%m") == month]
        items = _items(df)
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/orders")
    def orders_endpoint(
        account: list[str] | None = Query(None),
        status: list[str] | None = Query(None),
        start: date | None = None,
        end: date | None = None,
        search: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        df = orders(_engine(app), _list(account), start, end, _list(status), search)
        total = len(df)
        page = df.iloc[offset : offset + limit]
        items = _items(page)
        return {"items": items, "count": len(items), "total": total, "limit": limit, "offset": offset}

    @app.post("/api/v1/imports")
    async def imports_endpoint(account: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
        account = account.strip()
        if not account:
            raise HTTPException(status_code=422, detail="account is required")
        if account not in DEFAULT_ACCOUNTS:
            raise HTTPException(status_code=422, detail="account is not allowed")
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
                uploaded_by_label="API local",
                auth_method="local-api",
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

    return app


app = create_app()
