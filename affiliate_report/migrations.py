from __future__ import annotations

import hashlib
import inspect as pyinspect
from collections.abc import Callable
from uuid import UUID, uuid5

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, func, inspect, select, text
from sqlalchemy.engine import Connection, Engine

schema_metadata = MetaData()
schema_migrations = Table(
    "schema_migrations",
    schema_metadata,
    Column("version", Integer, primary_key=True),
    Column("name", String(128), nullable=False),
    Column("checksum", String(64), nullable=False),
    Column("applied_at", DateTime, nullable=False, server_default=func.now()),
)

# Chaquopy packages application modules as bytecode, so inspect.getsource isn't
# available on Android. These values are the source-derived checksums already
# used by desktop databases; keeping them preserves cross-runtime migration
# identity without weakening the existing checksum contract.
_PACKAGED_CHECKSUMS = {
    1: "b761a894e626ea804659b69e37ae5724be70b817d8dfae357bd7ed5f832be167",
    2: "2d82dc9116f6f23249a84e3f5c56ae93333841ed2729f65131e784765e115119",
    3: "5ecd41b319bb13533ddc251be8fe74270b21de8b608da47cc07f5a14c42f901f",
    4: "8be6c50ecb4ef9820369d6247137f775092abec4e150a1997416dcd3a5b6c2dd",
    5: "9ddcea91ecb2d89a1cb6a1e31d65b521d17bb65a13a3523c38850e98fa63c70a",
    6: "23943d9094c35ba074f6ea3a5368d84f7ec3cfc0e4ca678d51c81d684a37e05a",
    7: "637d1107e4c32466d3af141ce6a2fcc13788a32cb814aafe1679fa60000ec0fa",
    8: "498a271a1e2140f91870445c0181d6a2a5d6639bbbb6f5e0b34d27da14f3e080",
    9: "5421861e463299902337d2b7ab06455621361f31cd7f55001e4790787cda273b",
    10: "2f40e4529801e4e21dde58acaaadf0f88497d0fe2e63bd978004cfc5c357b404",
}


def apply_migrations(engine: Engine) -> None:
    schema_metadata.create_all(engine, tables=[schema_migrations])
    with engine.begin() as conn:
        _complete_partial_baseline(conn)
        applied = {row.version: row.checksum for row in conn.execute(select(schema_migrations.c.version, schema_migrations.c.checksum))}
        for migration in MIGRATIONS:
            checksum = _checksum(migration)
            if migration.version in applied:
                if applied[migration.version] != checksum:
                    raise RuntimeError(f"Migration {migration.version:04d} checksum mismatch")
                continue
            migration.run(conn)
            conn.execute(schema_migrations.insert().values(
                version=migration.version,
                name=migration.name,
                checksum=checksum,
            ))


class Migration:
    def __init__(self, version: int, name: str, run: Callable[[Connection], None]):
        self.version = version
        self.name = name
        self.run = run


def _checksum(migration: Migration) -> str:
    expected = _PACKAGED_CHECKSUMS.get(migration.version)
    try:
        source = pyinspect.getsource(migration.run)
    except (OSError, TypeError):
        if expected is None:
            raise RuntimeError(
                f"Migration {migration.version:04d} has no packaged checksum fallback"
            ) from None
        return expected

    payload = f"{migration.version}:{migration.name}:" + source
    calculated = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if expected is not None and calculated != expected:
        raise RuntimeError(f"Migration {migration.version:04d} source changed after release")
    return calculated


def _has_table(conn: Connection, name: str) -> bool:
    return inspect(conn).has_table(name)


def _columns(conn: Connection, table: str) -> set[str]:
    if not _has_table(conn, table):
        return set()
    return {col["name"] for col in inspect(conn).get_columns(table)}


def _indexes(conn: Connection, table: str) -> set[str]:
    if not _has_table(conn, table):
        return set()
    return {idx["name"] for idx in inspect(conn).get_indexes(table)}


def _complete_partial_baseline(conn: Connection) -> None:
    required = {"import_batches", "raw_import_rows", "order_line_versions", "monthly_targets"}
    present = {table for table in required if _has_table(conn, table)}
    if present and present != required:
        from .db import metadata

        metadata.create_all(conn)


def _migration_0001_baseline(conn: Connection) -> None:
    # Fresh DB: create the current baseline. Existing DB: adopt it without touching data.
    if not _has_table(conn, "import_batches"):
        from .db import metadata

        metadata.create_all(conn)


def _add_column(conn: Connection, table: str, name: str, ddl_type: str) -> None:
    if name not in _columns(conn, table):
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


def _migration_0002_import_audit_columns_and_indexes(conn: Connection) -> None:
    _add_column(conn, "import_batches", "uploaded_by_label", "VARCHAR(128)")
    _add_column(conn, "import_batches", "auth_method", "VARCHAR(64)")
    _add_column(conn, "import_batches", "auth_subject", "VARCHAR(255)")

    existing_batch_indexes = _indexes(conn, "import_batches")
    existing_raw_indexes = _indexes(conn, "raw_import_rows")
    if "ix_import_batches_account_created_at" not in existing_batch_indexes:
        conn.execute(text("CREATE INDEX ix_import_batches_account_created_at ON import_batches (account, created_at)"))
    if "ix_raw_import_rows_batch_id" not in existing_raw_indexes:
        conn.execute(text("CREATE INDEX ix_raw_import_rows_batch_id ON raw_import_rows (batch_id)"))


def _migration_0003_ensure_baseline_tables(conn: Connection) -> None:
    from .db import metadata

    metadata.create_all(conn)


def _migration_0004_auth_rbac_tables(conn: Connection) -> None:
    from .db import app_users, auth_sessions, metadata, oidc_login_states, user_account_access

    metadata.create_all(conn, tables=[app_users, user_account_access, auth_sessions, oidc_login_states])


def _migration_0005_account_registry_and_analytics_columns(conn: Connection) -> None:
    from .accounts import seed_accounts_from_existing
    from .db import accounts, metadata

    metadata.create_all(conn, tables=[accounts])
    seed_accounts_from_existing(conn)

    analytics = {
        "product_id": "ID sản phẩm",
        "shop_id": "Mã cửa hàng",
        "content_type": "Loại nội dung",
        "content_id": "Id nội dung",
        "order_type": "Loại đơn hàng",
        "commission_type": "Loại hoa hồng",
        "currency": "Đơn vị tiền tệ",
    }
    for column in analytics:
        _add_column(conn, "order_line_versions", column, "VARCHAR(128)")

    if _has_table(conn, "order_line_versions"):
        for column, raw_key in analytics.items():
            if conn.dialect.name == "postgresql":
                conn.execute(text(
                    f'UPDATE order_line_versions SET {column} = raw_json ->> :raw_key '
                    f'WHERE {column} IS NULL AND raw_json IS NOT NULL'
                ), {"raw_key": raw_key})
            else:
                conn.execute(text(
                    f'UPDATE order_line_versions SET {column} = json_extract(raw_json, :path) '
                    f'WHERE {column} IS NULL AND raw_json IS NOT NULL AND json_valid(raw_json)'
                ), {"path": f'$."{raw_key}"'})

    existing = _indexes(conn, "order_line_versions")
    if "ix_order_line_versions_product_id" not in existing:
        conn.execute(text("CREATE INDEX ix_order_line_versions_product_id ON order_line_versions (product_id)"))
    if "ix_order_line_versions_shop_id" not in existing:
        conn.execute(text("CREATE INDEX ix_order_line_versions_shop_id ON order_line_versions (shop_id)"))
    if "ix_order_line_versions_content_id" not in existing:
        conn.execute(text("CREATE INDEX ix_order_line_versions_content_id ON order_line_versions (content_id)"))


def _migration_0006_rename_target_commission(conn: Connection) -> None:
    # Cột tên là target_commission nhưng giá trị luôn là KPI mỗi ngày; đổi tên để đọc code
    # không còn phải nhớ ngoại lệ. Database mới đã tạo sẵn tên đúng nên bước này bỏ qua.
    columns = _columns(conn, "monthly_targets")
    if "daily_target_commission" in columns or "target_commission" not in columns:
        return
    conn.execute(text("ALTER TABLE monthly_targets RENAME COLUMN target_commission TO daily_target_commission"))

def _migration_0007_ui_preferences_saved_views(conn: Connection) -> None:
    from .db import metadata, saved_report_views, user_ui_preferences
    metadata.create_all(conn, tables=[user_ui_preferences, saved_report_views])


def _migration_0008_drop_duplicate_raw_json(conn: Connection) -> None:
    """Bỏ order_line_versions.raw_json — bản sao thứ hai của cùng một chuỗi JSON.

    Đo trên database thật: 45,7 MB cho 5.508 dòng, trong đó raw_import_rows.raw_json 12,8 MB và
    order_line_versions.raw_json 12,8 MB. So 200 cặp cùng business_key: 200/200 giống hệt nhau
    từng byte.

    Cột này chỉ được GHI, không nơi nào đọc: imports.undo_import và imports.order_line_history
    không đụng tới, order_line_history chọn cột tường minh, reports.py loại nó khỏi báo cáo bằng
    tên, và giao diện web không nhắc tới. JSON gốc vẫn còn nguyên trong raw_import_rows, nơi
    phục vụ audit và hoàn tác lần nhập — nên bỏ đi không mất khả năng nào.

    Migration 0005 từng backfill các cột chuẩn hoá TỪ cột này; nó chạy trước migration này theo
    thứ tự nên vẫn có dữ liệu để đọc.
    """
    if "raw_json" not in _columns(conn, "order_line_versions"):
        return
    # KHÔNG dùng DROP COLUMN: migration 0005 backfill các cột chuẩn hoá TỪ cột này và có guard
    # checksum chống sửa migration đã áp dụng, nên cột phải còn tồn tại lúc 0005 chạy. Cũng
    # không đặt NULL được vì database cũ khai báo NOT NULL. Ghi rỗng là đủ thu hồi chỗ; '""' là
    # đúng thứ SQLAlchemy ghi cho chuỗi rỗng ở cột kiểu JSON.
    #
    # Không lọc "WHERE raw_json <> ..." dù chỉ cần ghi các dòng còn dữ liệu: kiểu json của
    # PostgreSQL không có toán tử so sánh nên mệnh đề đó đổ ngay. Migration chạy đúng một lần,
    # ghi cả bảng không đắt hơn đáng kể mà chạy được trên cả hai hệ.
    conn.execute(text("""UPDATE order_line_versions SET raw_json = '""'"""))


_SYNC_NAMESPACE = UUID("35788392-f297-47bb-8f2f-0a6a8e5af910")


def _migration_0009_local_device_sync(conn: Connection) -> None:
    from .db import (
        accounts,
        device_identity,
        ensure_device_identity,
        import_batches,
        metadata,
        monthly_targets,
        sync_history,
        sync_tombstones,
    )

    metadata.create_all(conn, tables=[device_identity, sync_tombstones, sync_history])
    identity = ensure_device_identity(conn)
    device_id = identity["device_id"]

    for name, ddl_type in (
        ("sync_id", "VARCHAR(36)"),
        ("source_device_id", "VARCHAR(36)"),
        ("source_created_at", "TIMESTAMP"),
    ):
        _add_column(conn, "import_batches", name, ddl_type)
    for name, ddl_type in (
        ("sync_id", "VARCHAR(36)"),
        ("source_device_id", "VARCHAR(36)"),
        ("sync_updated_at", "TIMESTAMP"),
    ):
        _add_column(conn, "accounts", name, ddl_type)
    for name, ddl_type in (
        ("sync_id", "VARCHAR(36)"),
        ("source_device_id", "VARCHAR(36)"),
        ("sync_updated_at", "TIMESTAMP"),
    ):
        _add_column(conn, "monthly_targets", name, ddl_type)

    for row in conn.execute(select(import_batches.c.id, import_batches.c.file_sha, import_batches.c.created_at, import_batches.c.sync_id)):
        if row.sync_id:
            continue
        stable_id = str(uuid5(_SYNC_NAMESPACE, f"batch:{device_id}:{row.id}:{row.file_sha}"))
        conn.execute(
            import_batches.update().where(import_batches.c.id == row.id).values(
                sync_id=stable_id,
                source_device_id=device_id,
                source_created_at=row.created_at or func.now(),
            )
        )
    for row in conn.execute(select(accounts.c.code, accounts.c.updated_at, accounts.c.sync_id)):
        values = {
            "source_device_id": device_id,
            "sync_updated_at": row.updated_at or func.now(),
        }
        if not row.sync_id:
            values["sync_id"] = str(uuid5(_SYNC_NAMESPACE, f"account:{device_id}:{row.code}"))
        conn.execute(accounts.update().where(accounts.c.code == row.code).values(**values))
    for row in conn.execute(select(monthly_targets.c.id, monthly_targets.c.account, monthly_targets.c.month, monthly_targets.c.sync_id)):
        if row.sync_id:
            continue
        stable_id = str(uuid5(_SYNC_NAMESPACE, f"target:{device_id}:{row.id}:{row.account}:{row.month}"))
        conn.execute(
            monthly_targets.update().where(monthly_targets.c.id == row.id).values(
                sync_id=stable_id,
                source_device_id=device_id,
                sync_updated_at=func.now(),
            )
        )

    if "uq_import_batches_sync_id" not in _indexes(conn, "import_batches"):
        conn.execute(text("CREATE UNIQUE INDEX uq_import_batches_sync_id ON import_batches (sync_id)"))
    if "uq_accounts_sync_id" not in _indexes(conn, "accounts"):
        conn.execute(text("CREATE UNIQUE INDEX uq_accounts_sync_id ON accounts (sync_id)"))
    if "uq_monthly_targets_sync_id" not in _indexes(conn, "monthly_targets"):
        conn.execute(text("CREATE UNIQUE INDEX uq_monthly_targets_sync_id ON monthly_targets (sync_id)"))


def _migration_0010_deterministic_sync_identity(conn: Connection) -> None:
    """Give the same logical record one identity on every local device."""
    from .db import (
        account_sync_id,
        accounts,
        import_batch_sync_id,
        import_batches,
        monthly_targets,
        sync_tombstones,
        target_sync_id,
    )

    def replace_tombstone(entity_type: str, old_key: str | None, new_key: str) -> None:
        if not old_key or old_key == new_key:
            return
        old = conn.execute(select(sync_tombstones).where(
            sync_tombstones.c.entity_type == entity_type,
            sync_tombstones.c.entity_key == old_key,
        )).mappings().first()
        if not old:
            return
        current = conn.execute(select(sync_tombstones).where(
            sync_tombstones.c.entity_type == entity_type,
            sync_tombstones.c.entity_key == new_key,
        )).mappings().first()
        if current:
            use_old = old["deleted_at"] >= current["deleted_at"]
            conn.execute(sync_tombstones.update().where(sync_tombstones.c.id == current["id"]).values(
                deleted_at=old["deleted_at"] if use_old else current["deleted_at"],
                source_device_id=old["source_device_id"] if use_old else current["source_device_id"],
            ))
            conn.execute(sync_tombstones.delete().where(sync_tombstones.c.id == old["id"]))
        else:
            conn.execute(sync_tombstones.update().where(sync_tombstones.c.id == old["id"]).values(entity_key=new_key))

    for row in conn.execute(select(accounts.c.code, accounts.c.sync_id)):
        stable_id = account_sync_id(row.code)
        replace_tombstone("account", row.sync_id, stable_id)
        conn.execute(accounts.update().where(accounts.c.code == row.code).values(sync_id=stable_id))
    for row in conn.execute(select(monthly_targets.c.id, monthly_targets.c.account, monthly_targets.c.month, monthly_targets.c.sync_id)):
        stable_id = target_sync_id(row.account, row.month)
        replace_tombstone("target", row.sync_id, stable_id)
        conn.execute(monthly_targets.update().where(monthly_targets.c.id == row.id).values(sync_id=stable_id))
    for row in conn.execute(select(import_batches.c.id, import_batches.c.account, import_batches.c.file_sha, import_batches.c.sync_id)):
        stable_id = import_batch_sync_id(row.account, row.file_sha)
        replace_tombstone("import_batch", row.sync_id, stable_id)
        conn.execute(import_batches.update().where(import_batches.c.id == row.id).values(sync_id=stable_id))


MIGRATIONS = [
    Migration(1, "baseline_create_or_adopt", _migration_0001_baseline),
    Migration(2, "import_audit_columns_and_indexes", _migration_0002_import_audit_columns_and_indexes),
    Migration(3, "ensure_baseline_tables", _migration_0003_ensure_baseline_tables),
    Migration(4, "auth_rbac_tables", _migration_0004_auth_rbac_tables),
    Migration(5, "account_registry_and_analytics_columns", _migration_0005_account_registry_and_analytics_columns),
    Migration(6, "rename_target_commission_to_daily", _migration_0006_rename_target_commission),
    Migration(7, "ui_preferences_saved_views", _migration_0007_ui_preferences_saved_views),
    Migration(8, "drop_duplicate_raw_json", _migration_0008_drop_duplicate_raw_json),
    Migration(9, "local_device_sync", _migration_0009_local_device_sync),
    Migration(10, "deterministic_sync_identity", _migration_0010_deterministic_sync_identity),
]


def main() -> None:
    from .db import get_engine

    apply_migrations(get_engine())


if __name__ == "__main__":
    main()
