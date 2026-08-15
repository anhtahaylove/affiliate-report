from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Connection, Engine

from .db import account_sync_id, accounts, ensure_device_identity, import_batches, monthly_targets, order_line_versions, raw_import_rows, record_sync_tombstone, sync_tombstones, user_account_access

# Chấp nhận cả dấu chấm: username TikTok thật thường có dạng "sarah.reign". CHỈ thêm dấu chấm,
# không thêm chữ thường — giá trị đưa vào đây LUÔN đã qua .upper() trước (xem _normalize_code
# bên dưới). api.py:_sanitize_view_filters dùng lại đúng hằng số này để kiểm giá trị filter THÔ
# (chưa chuẩn hoá): "all" (thường) phải bị chặn ở đây vì so sánh "!= 'ALL'" ở đó phân biệt hoa
# thường và không tự bắt được — thêm A-Za-z từng làm "all" lọt qua cả hai lớp kiểm tra.
ACCOUNT_CODE_RE = re.compile(r"^[A-Z0-9_.-]{1,64}$")


@dataclass(frozen=True)
class Account:
    code: str
    display_name: str
    active: bool
    display_order: int
    created_at: Any = None
    updated_at: Any = None


def list_accounts(engine: Engine, include_inactive: bool = False) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        stmt = select(accounts)
        if not include_inactive:
            stmt = stmt.where(accounts.c.active.is_(True))
        rows = conn.execute(stmt.order_by(accounts.c.display_order, accounts.c.code)).mappings().all()
    return [dict(row) for row in rows]


def active_account_codes(engine: Engine) -> tuple[str, ...]:
    return tuple(row["code"] for row in list_accounts(engine))


def create_account(
    engine: Engine,
    code: str,
    *,
    display_name: str | None = None,
    active: bool = True,
    display_order: int | None = None,
) -> dict[str, Any]:
    code = _normalize_code(code)
    display_name = _display_name(display_name, code)
    with engine.begin() as conn:
        order = _next_order(conn) if display_order is None else int(display_order)
        device_id = ensure_device_identity(conn)["device_id"]
        conn.execute(accounts.insert().values(
            code=code,
            sync_id=account_sync_id(code),
            display_name=display_name,
            active=active,
            display_order=order,
            updated_at=func.now(),
            source_device_id=device_id,
            sync_updated_at=func.now(),
        ))
        conn.execute(delete(sync_tombstones).where(
            sync_tombstones.c.entity_type == "account",
            sync_tombstones.c.entity_key == account_sync_id(code),
        ))
        return _get_account(conn, code)


def update_account(
    engine: Engine,
    code: str,
    *,
    display_name: str | None = None,
    active: bool | None = None,
    display_order: int | None = None,
) -> dict[str, Any]:
    code = _normalize_code(code)
    values: dict[str, Any] = {"updated_at": func.now()}
    if display_name is not None:
        values["display_name"] = _display_name(display_name, code)
    if active is not None:
        values["active"] = bool(active)
    if display_order is not None:
        values["display_order"] = int(display_order)
    with engine.begin() as conn:
        values["source_device_id"] = ensure_device_identity(conn)["device_id"]
        values["sync_updated_at"] = func.now()
        result = conn.execute(update(accounts).where(accounts.c.code == code).values(**values))
        if result.rowcount == 0:
            raise LookupError("Không tìm thấy account.")
        return _get_account(conn, code)


def delete_account_preview(engine: Engine, code: str) -> dict[str, Any]:
    code = _normalize_code(code)
    with engine.connect() as conn:
        exists = conn.execute(select(accounts.c.code).where(accounts.c.code == code)).first() is not None
        deps = _dependency_counts(conn, code)
    return {
        "code": code,
        "exists": exists,
        "dependency_counts": deps,
        "can_hard_delete": exists and can_hard_delete_accounts(engine),
        "postgres_action": "archive",
    }


def delete_account(engine: Engine, code: str, *, hard: bool = False) -> dict[str, Any]:
    code = _normalize_code(code)
    if not hard or not can_hard_delete_accounts(engine):
        archived = update_account(engine, code, active=False)
        return {
            "code": code,
            "archived": True,
            "hard_deleted": False,
            "account": archived,
            "dependency_counts": delete_account_preview(engine, code)["dependency_counts"],
        }
    from .reset_data import backup_sqlite_before_change

    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            # Dùng chung đường sao lưu với reset/restore/hoàn tác: cùng cách kiểm tra và cùng
            # chính sách chỉ giữ lại vài bản gần nhất.
            backup_path = backup_sqlite_before_change(engine, "delete-account")
            deps = _dependency_counts(conn, code)
            batch_ids = select(import_batches.c.id).where(import_batches.c.account == code)
            conn.execute(delete(raw_import_rows).where(raw_import_rows.c.batch_id.in_(batch_ids)))
            conn.execute(delete(order_line_versions).where(order_line_versions.c.account == code))
            conn.execute(delete(import_batches).where(import_batches.c.account == code))
            conn.execute(delete(user_account_access).where(user_account_access.c.account == code))
            conn.execute(delete(monthly_targets).where(monthly_targets.c.account == code))
            account_sync_id = conn.execute(
                select(accounts.c.sync_id).where(accounts.c.code == code)
            ).scalar_one_or_none()
            if account_sync_id:
                record_sync_tombstone(conn, "account", account_sync_id)
            result = conn.execute(delete(accounts).where(accounts.c.code == code))
            if result.rowcount == 0:
                raise LookupError("Không tìm thấy account.")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "code": code,
        "archived": False,
        "hard_deleted": True,
        "backup_path": str(backup_path),
        "dependency_counts": deps,
    }


def archive_account(engine: Engine, code: str) -> dict[str, Any]:
    return delete_account(engine, code, hard=False)


def can_hard_delete_accounts(engine: Engine) -> bool:
    return _is_file_backed_sqlite(engine)


def seed_accounts_from_existing(conn: Connection) -> None:
    existing = set(conn.execute(select(accounts.c.code)).scalars().all())
    found: set[str] = set()
    for table in (import_batches, order_line_versions, monthly_targets, user_account_access):
        if table.name == monthly_targets.name:
            values = conn.execute(select(table.c.account).where(table.c.account != "ALL")).scalars().all()
        else:
            values = conn.execute(select(table.c.account)).scalars().all()
        for value in values:
            if not value:
                continue
            try:
                found.add(_normalize_code(value))
            except ValueError:
                continue
    for offset, code in enumerate(sorted(found - existing), start=_next_order(conn)):
        conn.execute(accounts.insert().values(
            code=code,
            display_name=code,
            active=True,
            display_order=offset,
            updated_at=func.now(),
        ))


def _normalize_code(code: str) -> str:
    value = (code or "").strip().upper()
    if value == "ALL":
        raise ValueError("ALL là mã tổng hợp nội bộ, không được dùng làm affiliate account.")
    if not ACCOUNT_CODE_RE.fullmatch(value):
        raise ValueError("Account code phải dài 1-64 ký tự và chỉ gồm A-Z, 0-9, _, - hoặc dấu chấm.")
    return value


def _display_name(value: str | None, code: str) -> str:
    text = (value or code).strip()
    if not text:
        raise ValueError("display_name không được để trống.")
    if len(text) > 128:
        raise ValueError("display_name không được dài quá 128 ký tự.")
    return text


def _next_order(conn: Connection) -> int:
    value = conn.execute(select(func.max(accounts.c.display_order))).scalar()
    return int(value or 0) + 10


def _get_account(conn: Connection, code: str) -> dict[str, Any]:
    row = conn.execute(select(accounts).where(accounts.c.code == code)).mappings().first()
    if not row:
        raise LookupError("Không tìm thấy account.")
    return dict(row)


def _dependency_counts(conn: Connection, code: str) -> dict[str, int]:
    batch_ids = select(import_batches.c.id).where(import_batches.c.account == code)
    return {
        "raw_import_rows": int(conn.execute(select(func.count()).select_from(raw_import_rows).where(raw_import_rows.c.batch_id.in_(batch_ids))).scalar_one()),
        "import_batches": int(conn.execute(select(func.count()).select_from(import_batches).where(import_batches.c.account == code)).scalar_one()),
        "order_line_versions": int(conn.execute(select(func.count()).select_from(order_line_versions).where(order_line_versions.c.account == code)).scalar_one()),
        "monthly_targets": int(conn.execute(select(func.count()).select_from(monthly_targets).where(monthly_targets.c.account == code)).scalar_one()),
        "user_account_access": int(conn.execute(select(func.count()).select_from(user_account_access).where(user_account_access.c.account == code)).scalar_one()),
    }


def _is_file_backed_sqlite(engine: Engine) -> bool:
    if engine.dialect.name != "sqlite":
        return False
    database = engine.url.database
    if not database or database == ":memory:":
        return False
    return Path(database).expanduser().exists()


def _sqlite_file_path(engine: Engine) -> Path:
    if engine.dialect.name != "sqlite":
        raise ValueError("Hard delete is only available for local SQLite.")
    database = engine.url.database
    if not database or database == ":memory:":
        raise ValueError("Hard delete requires a file-backed SQLite database.")
    path = Path(database).expanduser().resolve()
    if not path.exists():
        raise ValueError("SQLite database file does not exist.")
    return path
