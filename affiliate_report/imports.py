"""Hoàn tác một lần nhập và đọc lịch sử phiên bản của một dòng đơn.

Database đã lưu sẵn mọi phiên bản của từng dòng đơn kèm batch tạo ra nó, nên gỡ đúng một lần
nhập chỉ là xoá các phiên bản thuộc batch đó rồi trả cờ `is_current` về phiên bản còn lại mới
nhất — không cần khôi phục toàn bộ database.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.engine import Engine

from .db import import_batches, order_line_versions, raw_import_rows, record_sync_tombstone
from .reset_data import backup_sqlite_before_change

UNDO_CONFIRMATION_PREFIX = "HOAN TAC"
_KEY_CHUNK = 500


def undo_confirmation_phrase(batch_id: int) -> str:
    return f"{UNDO_CONFIRMATION_PREFIX} {batch_id}"


def _chunks(values: list[str]) -> list[list[str]]:
    return [values[offset : offset + _KEY_CHUNK] for offset in range(0, len(values), _KEY_CHUNK)]


def _batch(conn, batch_id: int) -> dict[str, Any]:
    row = conn.execute(select(import_batches).where(import_batches.c.id == batch_id)).mappings().first()
    if not row:
        raise LookupError("Không tìm thấy lần nhập.")
    return dict(row)


def _batch_keys(conn, batch_id: int) -> list[str]:
    stmt = select(order_line_versions.c.business_key).where(order_line_versions.c.batch_id == batch_id).distinct()
    return [str(key) for key in conn.execute(stmt).scalars()]


def _newer_batches(conn, account: str, batch_id: int) -> int:
    stmt = select(func.count()).select_from(import_batches).where(
        import_batches.c.account == account,
        import_batches.c.id > batch_id,
    )
    return int(conn.execute(stmt).scalar_one())


def undo_preview(engine: Engine, batch_id: int) -> dict[str, Any]:
    with engine.connect() as conn:
        batch = _batch(conn, batch_id)
        keys = _batch_keys(conn, batch_id)
        removed_versions = int(conn.execute(
            select(func.count()).select_from(order_line_versions).where(order_line_versions.c.batch_id == batch_id)
        ).scalar_one())
        removed_raw_rows = int(conn.execute(
            select(func.count()).select_from(raw_import_rows).where(raw_import_rows.c.batch_id == batch_id)
        ).scalar_one())

        removed_lines = 0
        restored_lines = 0
        for chunk in _chunks(keys):
            with_history = set(conn.execute(
                select(order_line_versions.c.business_key)
                .where(order_line_versions.c.business_key.in_(chunk), order_line_versions.c.batch_id != batch_id)
                .distinct()
            ).scalars())
            current_here = set(conn.execute(
                select(order_line_versions.c.business_key).where(
                    order_line_versions.c.business_key.in_(chunk),
                    order_line_versions.c.batch_id == batch_id,
                    order_line_versions.c.is_current.is_(True),
                )
            ).scalars())
            removed_lines += len(set(chunk) - with_history)
            restored_lines += len(with_history & current_here)

        newer_batches = _newer_batches(conn, str(batch["account"]), batch_id)

    return {
        "batch_id": batch_id,
        "account": batch["account"],
        "filename": batch["filename"],
        "created_at": batch["created_at"],
        "uploaded_by_label": batch["uploaded_by_label"],
        "is_latest": newer_batches == 0,
        "newer_batches": newer_batches,
        "removed_versions": removed_versions,
        "removed_raw_rows": removed_raw_rows,
        "removed_lines": removed_lines,
        "restored_lines": restored_lines,
        "confirmation": undo_confirmation_phrase(batch_id),
        "warning": None if newer_batches == 0 else (
            f"Đây không phải lần nhập mới nhất của {batch['account']}; còn {newer_batches} lần nhập mới hơn. "
            "Hoàn tác chỉ gỡ đúng các phiên bản của lần nhập này, số liệu hiện tại do lần nhập mới hơn quyết định."
        ),
    }


def undo_import(engine: Engine, batch_id: int, confirmation: str) -> dict[str, Any]:
    expected = undo_confirmation_phrase(batch_id)
    if confirmation != expected:
        raise ValueError(f"confirmation must be {expected!r}")

    preview = undo_preview(engine, batch_id)
    backup_path = backup_sqlite_before_change(engine, f"undo-import-{batch_id}")

    with engine.connect() as conn:
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            batch = _batch(conn, batch_id)
            keys = _batch_keys(conn, batch_id)
            removed_versions = conn.execute(
                delete(order_line_versions).where(order_line_versions.c.batch_id == batch_id)
            ).rowcount or 0

            restored_lines = 0
            removed_lines = 0
            newest = order_line_versions.alias("newest")
            still_current = order_line_versions.alias("still_current")
            for chunk in _chunks(keys):
                # Chỉ nâng phiên bản còn lại mới nhất lên current khi khoá đó không còn dòng
                # current nào — lần nhập mới hơn đè lên vẫn phải giữ nguyên quyền quyết định.
                promote = (
                    update(order_line_versions)
                    .where(
                        order_line_versions.c.business_key.in_(chunk),
                        order_line_versions.c.is_current.is_(False),
                        order_line_versions.c.version == (
                            select(func.max(newest.c.version))
                            .where(newest.c.business_key == order_line_versions.c.business_key)
                            .scalar_subquery()
                        ),
                        ~exists(
                            select(still_current.c.id).where(
                                still_current.c.business_key == order_line_versions.c.business_key,
                                still_current.c.is_current.is_(True),
                            )
                        ),
                    )
                    .values(is_current=True)
                )
                restored_lines += conn.execute(promote).rowcount or 0
                remaining = set(conn.execute(
                    select(order_line_versions.c.business_key)
                    .where(order_line_versions.c.business_key.in_(chunk))
                    .distinct()
                ).scalars())
                removed_lines += len(set(chunk) - remaining)

            removed_raw_rows = conn.execute(
                delete(raw_import_rows).where(raw_import_rows.c.batch_id == batch_id)
            ).rowcount or 0
            if batch.get("sync_id"):
                record_sync_tombstone(conn, "import_batch", str(batch["sync_id"]))
            if conn.execute(delete(import_batches).where(import_batches.c.id == batch_id)).rowcount == 0:
                raise LookupError("Không tìm thấy lần nhập.")
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "batch_id": batch_id,
        "account": preview["account"],
        "filename": preview["filename"],
        "removed_versions": removed_versions,
        "removed_raw_rows": removed_raw_rows,
        "removed_lines": removed_lines,
        "restored_lines": restored_lines,
        "backup_path": backup_path,
    }


def order_line_history(engine: Engine, business_key: str) -> list[dict[str, Any]]:
    stmt = (
        select(
            order_line_versions.c.version,
            order_line_versions.c.is_current,
            order_line_versions.c.account,
            order_line_versions.c.order_id,
            order_line_versions.c.sku_id,
            order_line_versions.c.status,
            order_line_versions.c.gmv,
            order_line_versions.c.units_sold,
            order_line_versions.c.units_refunded,
            order_line_versions.c.estimated_commission,
            order_line_versions.c.final_received,
            order_line_versions.c.order_date,
            order_line_versions.c.settlement_date,
            order_line_versions.c.created_at.label("recorded_at"),
            order_line_versions.c.batch_id,
            import_batches.c.filename,
            import_batches.c.uploaded_by_label,
        )
        .select_from(
            order_line_versions.join(
                import_batches,
                import_batches.c.id == order_line_versions.c.batch_id,
                isouter=True,
            )
        )
        .where(order_line_versions.c.business_key == business_key)
        .order_by(order_line_versions.c.version.desc())
    )
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings()]
