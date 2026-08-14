from __future__ import annotations

import json
import os
import platform
import re
import socket
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

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
    delete,
    event,
    func,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .parser import file_sha256

DEFAULT_DATABASE_URL = "sqlite:///data/affiliate_report.db"
ACCOUNT_CODE_RE = re.compile(r"^[A-Z0-9_-]{1,64}$")
SYNC_ID_NAMESPACE = UUID("35788392-f297-47bb-8f2f-0a6a8e5af910")
ANALYTICS_RAW_FIELDS = {
    "product_id": "ID sản phẩm",
    "shop_id": "Mã cửa hàng",
    "content_type": "Loại nội dung",
    "content_id": "Id nội dung",
    "order_type": "Loại đơn hàng",
    "commission_type": "Loại hoa hồng",
    "currency": "Đơn vị tiền tệ",
}


def account_sync_id(code: str) -> str:
    return str(uuid5(SYNC_ID_NAMESPACE, f"account:{code.strip().upper()}"))


def target_sync_id(account: str, month: Any) -> str:
    month_text = month.isoformat() if hasattr(month, "isoformat") else str(month)
    return str(uuid5(SYNC_ID_NAMESPACE, f"target:{account.strip().upper()}:{month_text[:10]}"))


def import_batch_sync_id(account: str, file_sha: str) -> str:
    return str(uuid5(SYNC_ID_NAMESPACE, f"batch:{account.strip().upper()}:{file_sha.lower()}"))
metadata = MetaData()

accounts = Table(
    "accounts", metadata,
    Column("code", String(64), primary_key=True),
    Column("sync_id", String(36), unique=True),
    Column("display_name", String(128), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("display_order", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("source_device_id", String(36)),
    Column("sync_updated_at", DateTime(timezone=True)),
)
Index("ix_accounts_active_order", accounts.c.active, accounts.c.display_order, accounts.c.code)

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
    Column("sync_id", String(36)),
    Column("source_device_id", String(36)),
    Column("source_created_at", DateTime(timezone=True)),
    UniqueConstraint("account", "file_sha", name="uq_import_batch_account_file"),
    UniqueConstraint("sync_id", name="uq_import_batches_sync_id"),
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
    Column("product_id", String(128)),
    Column("product_name", Text),
    Column("shop_id", String(128)),
    Column("shop_name", Text),
    Column("content_type", String(128)),
    Column("content_id", String(128)),
    Column("order_type", String(128)),
    Column("commission_type", String(128)),
    Column("currency", String(32)),
    Column("status", String(32), nullable=False),
    Column("order_date", DateTime),
    Column("settlement_date", DateTime),
    Column("gmv", BigInteger, nullable=False, default=0),
    Column("units_sold", Integer, nullable=False, default=0),
    Column("units_refunded", Integer, nullable=False, default=0),
    Column("estimated_commission", BigInteger, nullable=False, default=0),
    Column("final_received", BigInteger),
    Column("normalized_hash", String(64), nullable=False),
    # Từ migration 8 cột này để rỗng: raw_import_rows đã giữ nguyên chuỗi JSON gốc cho audit
    # và hoàn tác, còn bản sao ở đây chỉ được ghi chứ không nơi nào đọc — đo được chiếm 28%
    # database. Không bỏ hẳn cột vì hai lẽ: migration 0005 backfill các cột chuẩn hoá TỪ nó và
    # migration đã áp dụng thì không được sửa, còn database cũ khai báo cột NOT NULL mà SQLite
    # không đổi được ràng buộc. default="" để lệnh chèn không cần nhắc tới nó nữa.
    Column("raw_json", JSON, nullable=False, default=""),
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
Index("ix_order_line_versions_product_id", order_line_versions.c.product_id)
Index("ix_order_line_versions_shop_id", order_line_versions.c.shop_id)
Index("ix_order_line_versions_content_id", order_line_versions.c.content_id)

monthly_targets = Table(
    "monthly_targets", metadata,
    Column("id", Integer, primary_key=True),
    Column("account", String(64), nullable=False),
    Column("month", Date, nullable=False),
    Column("daily_target_commission", BigInteger, nullable=False),
    Column("sync_id", String(36)),
    Column("source_device_id", String(36)),
    Column("sync_updated_at", DateTime(timezone=True)),
    UniqueConstraint("account", "month", name="uq_target_account_month"),
    UniqueConstraint("sync_id", name="uq_monthly_targets_sync_id"),
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

user_ui_preferences = Table(
    "user_ui_preferences", metadata,
    Column("principal_key", String(160), primary_key=True),
    Column("app_user_id", Integer, ForeignKey("app_users.id", ondelete="CASCADE")),
    Column("theme", String(16), nullable=False, default="system"),
    Column("sidebar_collapsed", Boolean, nullable=False, default=False),
    Column("dashboard_layout_json", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("app_user_id", name="uq_ui_preferences_app_user"),
)

saved_report_views = Table(
    "saved_report_views", metadata,
    Column("id", Integer, primary_key=True),
    Column("principal_key", String(160), nullable=False),
    Column("app_user_id", Integer, ForeignKey("app_users.id", ondelete="CASCADE")),
    Column("route", String(32), nullable=False),
    Column("name", String(64), nullable=False),
    Column("filters_json", JSON, nullable=False),
    Column("is_default", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("principal_key", "route", "name", name="uq_saved_view_principal_route_name"),
)
Index("ix_saved_views_principal_route", saved_report_views.c.principal_key, saved_report_views.c.route)
Index(
    "uq_saved_view_default_principal_route",
    saved_report_views.c.principal_key,
    saved_report_views.c.route,
    unique=True,
    sqlite_where=saved_report_views.c.is_default.is_(True),
    postgresql_where=saved_report_views.c.is_default.is_(True),
)

device_identity = Table(
    "device_identity", metadata,
    Column("id", Integer, primary_key=True),
    Column("device_id", String(36), nullable=False, unique=True),
    Column("device_name", String(128), nullable=False),
    Column("platform", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("id = 1", name="ck_device_identity_singleton"),
)

sync_tombstones = Table(
    "sync_tombstones", metadata,
    Column("id", Integer, primary_key=True),
    Column("entity_type", String(32), nullable=False),
    Column("entity_key", String(512), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("source_device_id", String(36), nullable=False),
    CheckConstraint(
        "entity_type IN ('import_batch', 'account', 'target')",
        name="ck_sync_tombstone_entity_type",
    ),
    UniqueConstraint("entity_type", "entity_key", name="uq_sync_tombstone_entity"),
)
Index("ix_sync_tombstones_deleted_at", sync_tombstones.c.deleted_at)

sync_history = Table(
    "sync_history", metadata,
    Column("package_id", String(36), primary_key=True),
    Column("package_hash", String(64), nullable=False),
    Column("source_device_id", String(36), nullable=False),
    Column("direction", String(16), nullable=False),
    Column("summary_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("direction IN ('export', 'import')", name="ck_sync_history_direction"),
)
Index("ix_sync_history_created_at", sync_history.c.created_at)


def ensure_device_identity(conn) -> dict[str, Any]:
    """Trả danh tính bền vững của database hiện tại; không phụ thuộc tài khoản đăng nhập."""
    row = conn.execute(select(device_identity).where(device_identity.c.id == 1)).mappings().first()
    if row:
        return dict(row)
    values = {
        "id": 1,
        "device_id": str(uuid4()),
        "device_name": socket.gethostname()[:128] or "Affiliate Report",
        "platform": (platform.system() or "unknown").lower()[:32],
    }
    conn.execute(device_identity.insert().values(**values))
    return values


def record_sync_tombstone(conn, entity_type: str, entity_key: str) -> None:
    if entity_type not in {"import_batch", "account", "target"} or not entity_key:
        raise ValueError("Sync tombstone không hợp lệ.")
    device_id = ensure_device_identity(conn)["device_id"]
    existing = conn.execute(select(sync_tombstones.c.id).where(
        sync_tombstones.c.entity_type == entity_type,
        sync_tombstones.c.entity_key == entity_key,
    )).first()
    if existing:
        conn.execute(update(sync_tombstones).where(sync_tombstones.c.id == existing.id).values(
            deleted_at=func.now(), source_device_id=device_id,
        ))
    else:
        conn.execute(sync_tombstones.insert().values(
            entity_type=entity_type,
            entity_key=entity_key,
            source_device_id=device_id,
        ))


def _unicode_lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


def _register_sqlite_unicode_lower(dbapi_connection, _record) -> None:
    # lower() dựng sẵn của SQLite chỉ đổi hoa-thường cho ASCII, nên tìm "áo thun" sẽ không ra
    # "Áo Thun". Thay bằng str.lower của Python để tìm kiếm tiếng Việt khớp như PostgreSQL.
    dbapi_connection.create_function("lower", 1, _unicode_lower, deterministic=True)
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///").split("?", 1)[0]).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, future=True)
        event.listen(engine, "connect", _register_sqlite_unicode_lower)
        return engine
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


def _normalize_account_code(code: str) -> str:
    value = (code or "").strip().upper()
    if value == "ALL":
        raise ValueError("ALL là mã tổng hợp nội bộ, không được dùng làm affiliate account.")
    if not ACCOUNT_CODE_RE.fullmatch(value):
        raise ValueError("Affiliate account phải dài 1-64 ký tự và chỉ gồm A-Z, 0-9, _ hoặc -.")
    return value


def _ensure_account(conn, account: str) -> None:
    existing = conn.execute(select(accounts.c.code).where(accounts.c.code == account)).first()
    if existing:
        return
    order = int(conn.execute(select(func.max(accounts.c.display_order))).scalar() or 0) + 10
    identity = ensure_device_identity(conn)
    values = {
        "code": account,
        "sync_id": account_sync_id(account),
        "display_name": account,
        "active": True,
        "display_order": order,
        "updated_at": func.now(),
        "source_device_id": identity["device_id"],
        "sync_updated_at": func.now(),
    }
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(accounts).values(**values).on_conflict_do_nothing(index_elements=["code"])
    else:
        from sqlalchemy.dialects.sqlite import insert

        stmt = insert(accounts).values(**values).on_conflict_do_nothing(index_elements=["code"])
    conn.execute(stmt)
    conn.execute(delete(sync_tombstones).where(
        sync_tombstones.c.entity_type == "account",
        sync_tombstones.c.entity_key == account_sync_id(account),
    ))


IMPORT_BATCH_SIZE = 1000
_LOOKUP_CHUNK = 500


def _current_versions(conn, business_keys) -> dict[str, tuple[int, str, int]]:
    """Một truy vấn lấy sẵn phiên bản hiện tại của mọi business_key trong file, thay cho
    một SELECT riêng cho từng dòng."""
    found: dict[str, tuple[int, str, int]] = {}
    keys = list(business_keys)
    for offset in range(0, len(keys), _LOOKUP_CHUNK):
        stmt = select(
            order_line_versions.c.id,
            order_line_versions.c.business_key,
            order_line_versions.c.normalized_hash,
            order_line_versions.c.version,
        ).where(
            order_line_versions.c.business_key.in_(keys[offset : offset + _LOOKUP_CHUNK]),
            order_line_versions.c.is_current.is_(True),
        )
        for row in conn.execute(stmt):
            found[row.business_key] = (row.id, row.normalized_hash, row.version)
    return found


def _write_plans(conn, plans: list[dict[str, Any]]) -> None:
    raws = [plan["raw"] for plan in plans]
    supersede = [plan["supersede_id"] for plan in plans if plan["supersede_id"] is not None]
    versions = [plan["version_values"] for plan in plans if plan["version_values"] is not None]
    if raws:
        conn.execute(raw_import_rows.insert(), raws)
    # Hạ cờ is_current trước khi chèn phiên bản mới, nếu không unique index một-dòng-hiện-tại
    # trên business_key sẽ bị vi phạm.
    if supersede:
        conn.execute(update(order_line_versions).where(order_line_versions.c.id.in_(supersede)).values(is_current=False))
    if versions:
        conn.execute(order_line_versions.insert(), versions)


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
    account = _normalize_account_code(account)
    hashes_by_key: dict[str, set[str]] = {}
    for row in rows:
        if row.get("_rejected"):
            continue
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
        _ensure_account(conn, account)
        identity = ensure_device_identity(conn)
        old_batch = conn.execute(
            select(import_batches).where(
                import_batches.c.account == account,
                import_batches.c.file_sha == sha,
            )
        ).mappings().first()
        if old_batch:
            return {"batch_id": old_batch["id"], "duplicate": True, "inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0}

        conn.execute(delete(sync_tombstones).where(
            sync_tombstones.c.entity_type == "import_batch",
            sync_tombstones.c.entity_key == import_batch_sync_id(account, sha),
        ))
        batch_id = conn.execute(import_batches.insert().values(
            file_sha=sha,
            filename=filename,
            account=account,
            uploaded_by_label=uploaded_by_label,
            auth_method=auth_method,
            auth_subject=auth_subject,
            sync_id=import_batch_sync_id(account, sha),
            source_device_id=identity["device_id"],
            source_created_at=func.now(),
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
        current_by_key = _current_versions(conn, hashes_by_key)
        plans: list[dict[str, Any]] = []
        for idx, row in enumerate(rows, start=2):
            # read_xlsx gắn số dòng thật trong file Excel; caller dựng rows thủ công thì dùng vị trí.
            row_number = int(row.get("_row_number") or idx)
            rejected = row.get("_rejected")
            if rejected:
                summary["rejected"] += 1
                summary["rejected_rows"].append(rejected)
                continue
            key = row["business_key"]
            raw = json.loads(json.dumps(
                row.get("_raw", row),
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ))
            plan: dict[str, Any] = {
                "row_number": row_number,
                "outcome": "unchanged",
                "raw": {"batch_id": batch_id, "row_number": row_number, "business_key": key, "raw_json": raw},
                "supersede_id": None,
                "version_values": None,
            }
            current = current_by_key.get(key)
            if not (current and current[1] == row["normalized_hash"]):
                plan["outcome"] = "updated" if current else "inserted"
                plan["supersede_id"] = current[0] if current else None
                plan["version_values"] = {
                    "business_key": key,
                    "account": account,
                    "order_id": row.get("ID đơn hàng"),
                    "sku_id": row.get("ID SKU"),
                    "product_id": row.get("product_id") or row.get("ID sản phẩm"),
                    "product_name": row.get("Tên sản phẩm"),
                    "shop_id": row.get("shop_id") or row.get("Mã cửa hàng"),
                    "shop_name": row.get("shop_name"),
                    "content_type": row.get("content_type") or row.get("Loại nội dung"),
                    "content_id": row.get("content_id") or row.get("Id nội dung"),
                    "order_type": row.get("order_type") or row.get("Loại đơn hàng"),
                    "commission_type": row.get("commission_type") or row.get("Loại hoa hồng"),
                    "currency": row.get("currency") or row.get("Đơn vị tiền tệ"),
                    "status": row.get("status", "unknown"),
                    "order_date": row.get("Ngày đặt hàng"),
                    "settlement_date": row.get("Ngày quyết toán hoa hồng"),
                    "gmv": row.get("gmv") or 0,
                    "units_sold": row.get("units_sold") or 0,
                    "units_refunded": row.get("units_refunded") or 0,
                    "estimated_commission": row.get("estimated_commission") or 0,
                    "final_received": row.get("final_received"),
                    "normalized_hash": row["normalized_hash"],
                    "is_current": True,
                    "version": (current[2] + 1) if current else 1,
                    "batch_id": batch_id,
                }
                # Cùng business_key xuất hiện lại trong một file chỉ có thể trùng hash (khác hash
                # đã bị chặn ở trên), nên id None ở đây không bao giờ được dùng để supersede.
                current_by_key[key] = (None, row["normalized_hash"], plan["version_values"]["version"])
            plans.append(plan)

        for offset in range(0, len(plans), IMPORT_BATCH_SIZE):
            chunk = plans[offset : offset + IMPORT_BATCH_SIZE]
            try:
                with conn.begin_nested():
                    _write_plans(conn, chunk)
            except IntegrityError:
                # Lô hỏng vì một vài dòng; chạy lại từng dòng để chỉ đúng dòng thật sự bị từ chối.
                for plan in chunk:
                    try:
                        with conn.begin_nested():
                            _write_plans(conn, [plan])
                    except IntegrityError:
                        plan["outcome"] = "rejected"
                        summary["rejected_rows"].append({
                            "row_number": plan["row_number"],
                            "reason": "Ràng buộc dữ liệu bị vi phạm",
                        })
            for plan in chunk:
                summary[plan["outcome"]] += 1

        summary["rejected_rows"].sort(key=lambda item: item["row_number"])
        conn.execute(update(import_batches).where(import_batches.c.id == batch_id).values(**{k: summary[k] for k in ("inserted", "updated", "unchanged", "rejected")}))
        return summary
