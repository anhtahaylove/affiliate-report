from __future__ import annotations

import hashlib
import inspect as pyinspect
from collections.abc import Callable

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
    payload = f"{migration.version}:{migration.name}:" + pyinspect.getsource(migration.run)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


MIGRATIONS = [
    Migration(1, "baseline_create_or_adopt", _migration_0001_baseline),
    Migration(2, "import_audit_columns_and_indexes", _migration_0002_import_audit_columns_and_indexes),
    Migration(3, "ensure_baseline_tables", _migration_0003_ensure_baseline_tables),
    Migration(4, "auth_rbac_tables", _migration_0004_auth_rbac_tables),
    Migration(5, "account_registry_and_analytics_columns", _migration_0005_account_registry_and_analytics_columns),
]


def main() -> None:
    from .db import get_engine

    apply_migrations(get_engine())


if __name__ == "__main__":
    main()
