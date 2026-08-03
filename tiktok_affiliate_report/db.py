from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .parser import file_sha256

DEFAULT_DATABASE_URL = "sqlite:///data/tiktok_affiliate_report.db"
DEFAULT_MONTHLY_TARGETS = {
    date(2026, 3, 1): 350000,
    date(2026, 4, 1): 400000,
    date(2026, 5, 1): 450000,
    date(2026, 6, 1): 500000,
    date(2026, 7, 1): 500000,
    date(2026, 8, 1): 500000,
}
metadata = MetaData()

import_batches = Table(
    "import_batches", metadata,
    Column("id", Integer, primary_key=True),
    Column("file_sha", String(64), nullable=False),
    Column("filename", String(255), nullable=False),
    Column("account", String(64), nullable=False),
    Column("uploaded_by_label", String(128)),
    Column("auth_method", String(64)),
    Column("auth_subject", String(255)),
    Column("inserted", Integer, nullable=False, default=0),
    Column("updated", Integer, nullable=False, default=0),
    Column("unchanged", Integer, nullable=False, default=0),
    Column("rejected", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint("account", "file_sha", name="uq_import_batch_account_file"),
)
Index("ix_import_batches_account_created_at", import_batches.c.account, import_batches.c.created_at)

raw_import_rows = Table(
    "raw_import_rows", metadata,
    Column("id", Integer, primary_key=True),
    Column("batch_id", Integer, ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False),
    Column("row_number", Integer, nullable=False),
    Column("business_key", String(512), nullable=False),
    Column("raw_json", JSON, nullable=False),
    CheckConstraint("row_number >= 2", name="ck_raw_import_row_number"),
    UniqueConstraint("batch_id", "row_number", name="uq_raw_import_batch_row"),
)
Index("ix_raw_import_rows_batch_id", raw_import_rows.c.batch_id)

order_line_versions = Table(
    "order_line_versions", metadata,
    Column("id", Integer, primary_key=True),
    Column("business_key", String(512), nullable=False),
    Column("account", String(64), nullable=False),
    Column("order_id", String(128)),
    Column("sku_id", String(128)),
    Column("product_name", Text),
    Column("shop_name", Text),
    Column("status", String(32), nullable=False),
    Column("order_date", DateTime),
    Column("settlement_date", DateTime),
    Column("gmv", BigInteger, nullable=False, default=0),
    Column("units_sold", Integer, nullable=False, default=0),
    Column("units_refunded", Integer, nullable=False, default=0),
    Column("estimated_commission", BigInteger, nullable=False, default=0),
    Column("final_received", BigInteger),
    Column("normalized_hash", String(64), nullable=False),
    Column("raw_json", JSON, nullable=False),
    Column("is_current", Boolean, nullable=False, default=True),
    Column("version", Integer, nullable=False, default=1),
    Column("batch_id", Integer, ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    CheckConstraint(
        "status IN ('settled', 'ineligible', 'pending', 'unknown')",
        name="ck_order_line_status",
    ),
    UniqueConstraint("business_key", "version", name="uq_order_line_version"),
)

Index(
    "ux_order_line_versions_current",
    order_line_versions.c.business_key,
    unique=True,
    sqlite_where=order_line_versions.c.is_current.is_(True),
    postgresql_where=order_line_versions.c.is_current.is_(True),
)
Index(
    "ix_order_line_versions_account_order_date",
    order_line_versions.c.account,
    order_line_versions.c.order_date,
    sqlite_where=order_line_versions.c.is_current.is_(True),
    postgresql_where=order_line_versions.c.is_current.is_(True),
)
Index("ix_order_line_versions_order_id", order_line_versions.c.order_id)
Index("ix_order_line_versions_sku_id", order_line_versions.c.sku_id)

monthly_targets = Table(
    "monthly_targets", metadata,
    Column("id", Integer, primary_key=True),
    Column("account", String(64), nullable=False),
    Column("month", Date, nullable=False),
    Column("target_commission", BigInteger, nullable=False),
    UniqueConstraint("account", "month", name="uq_target_account_month"),
)

app_users = Table(
    "app_users", metadata,
    Column("id", Integer, primary_key=True),
    Column("issuer", String(512), nullable=False),
    Column("subject", String(255), nullable=False),
    Column("email", String(320), nullable=False),
    Column("display_name", String(255)),
    Column("role", String(16), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("last_login_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("role IN ('owner', 'operator', 'viewer')", name="ck_app_user_role"),
    UniqueConstraint("issuer", "subject", name="uq_app_user_issuer_subject"),
)
Index("ix_app_users_email", app_users.c.email)

user_account_access = Table(
    "user_account_access", metadata,
    Column("user_id", Integer, ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True),
    Column("account", String(64), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_user_account_access_account", user_account_access.c.account)

auth_sessions = Table(
    "auth_sessions", metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False),
    Column("csrf_hash", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_auth_sessions_user_id", auth_sessions.c.user_id)
Index("ix_auth_sessions_expires_at", auth_sessions.c.expires_at)

oidc_login_states = Table(
    "oidc_login_states", metadata,
    Column("state_hash", String(64), primary_key=True),
    Column("code_verifier", String(255), nullable=False),
    Column("nonce", String(255), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_oidc_login_states_expires_at", oidc_login_states.c.expires_at)


def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///").split("?", 1)[0]).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, future=True)
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgresql+psycopg://"):
        return create_engine(url, future=True, pool_pre_ping=True)
    raise ValueError("DATABASE_URL phải dùng sqlite:/// hoặc postgresql+psycopg://.")


def init_db(engine: Engine) -> None:
    from .migrations import apply_migrations

    apply_migrations(engine)
    seed_targets(engine)


def seed_targets(engine: Engine) -> None:
    with engine.begin() as conn:
        for month, amount in DEFAULT_MONTHLY_TARGETS.items():
            values = {"account": "ALL", "month": month, "target_commission": amount}
            if engine.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
                stmt = insert(monthly_targets).values(**values).on_conflict_do_nothing(index_elements=["account", "month"])
            else:
                from sqlalchemy.dialects.sqlite import insert
                stmt = insert(monthly_targets).values(**values).on_conflict_do_nothing(index_elements=["account", "month"])
            conn.execute(stmt)


def import_rows(
    engine: Engine,
    *,
    filename: str,
    file_bytes: bytes,
    account: str,
    rows: list[dict[str, Any]],
    uploaded_by_label: str | None = None,
    auth_method: str | None = None,
    auth_subject: str | None = None,
) -> dict[str, Any]:
    hashes_by_key: dict[str, set[str]] = {}
    for row in rows:
        hashes_by_key.setdefault(row["business_key"], set()).add(row["normalized_hash"])
    collisions = [key for key, hashes in hashes_by_key.items() if len(hashes) > 1]
    if collisions:
        preview = ", ".join(collisions[:3])
        raise ValueError(f"File có {len(collisions)} business key trùng nhưng khác nội dung: {preview}")

    sha = file_sha256(file_bytes)
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"tiktok-affiliate-import:{account}"},
            )
        old_batch = conn.execute(
            select(import_batches).where(
                import_batches.c.account == account,
                import_batches.c.file_sha == sha,
            )
        ).mappings().first()
        if old_batch:
            return {"batch_id": old_batch["id"], "duplicate": True, "inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0}

        batch_id = conn.execute(import_batches.insert().values(
            file_sha=sha,
            filename=filename,
            account=account,
            uploaded_by_label=uploaded_by_label,
            auth_method=auth_method,
            auth_subject=auth_subject,
        )).inserted_primary_key[0]
        summary = {
            "batch_id": batch_id,
            "duplicate": False,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
            "rejected_rows": [],
        }
        for idx, row in enumerate(rows, start=2):
            try:
                outcome = None
                with conn.begin_nested():
                    raw = json.loads(json.dumps(
                        row.get("_raw", row),
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ))
                    conn.execute(raw_import_rows.insert().values(
                        batch_id=batch_id,
                        row_number=idx,
                        business_key=row["business_key"],
                        raw_json=raw,
                    ))
                    current = conn.execute(
                        select(order_line_versions)
                        .where(order_line_versions.c.business_key == row["business_key"], order_line_versions.c.is_current.is_(True))
                    ).mappings().first()
                    if current and current["normalized_hash"] == row["normalized_hash"]:
                        summary["unchanged"] += 1
                        continue
                    version = (current["version"] + 1) if current else 1
                    if current:
                        conn.execute(update(order_line_versions).where(order_line_versions.c.id == current["id"]).values(is_current=False))
                        outcome = "updated"
                    else:
                        outcome = "inserted"
                    conn.execute(order_line_versions.insert().values(
                        business_key=row["business_key"],
                        account=account,
                        order_id=row.get("ID đơn hàng"),
                        sku_id=row.get("ID SKU"),
                        product_name=row.get("Tên sản phẩm"),
                        shop_name=row.get("shop_name"),
                        status=row.get("status", "unknown"),
                        order_date=row.get("Ngày đặt hàng"),
                        settlement_date=row.get("Ngày quyết toán hoa hồng"),
                        gmv=row.get("gmv") or 0,
                        units_sold=row.get("units_sold") or 0,
                        units_refunded=row.get("units_refunded") or 0,
                        estimated_commission=row.get("estimated_commission") or 0,
                        final_received=row.get("final_received"),
                        normalized_hash=row["normalized_hash"],
                        raw_json=raw,
                        is_current=True,
                        version=version,
                        batch_id=batch_id,
                    ))
                summary[outcome] += 1
            except IntegrityError:
                summary["rejected"] += 1
                summary["rejected_rows"].append({
                    "row_number": idx,
                    "reason": "Ràng buộc dữ liệu bị vi phạm",
                })
        conn.execute(update(import_batches).where(import_batches.c.id == batch_id).values(**{k: summary[k] for k in ("inserted", "updated", "unchanged", "rejected")}))
        return summary
