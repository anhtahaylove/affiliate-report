from __future__ import annotations

from sqlalchemy import inspect, select, text

from tiktok_affiliate_report.db import get_engine, import_batches, import_rows, init_db, monthly_targets
from tiktok_affiliate_report.migrations import schema_migrations
from tests.test_imports import raw_row


def engine():
    return get_engine("sqlite:///:memory:")


def test_init_db_runs_versioned_migrations_and_seeds_targets():
    e = engine()

    init_db(e)
    init_db(e)

    inspector = inspect(e)
    assert inspector.has_table("schema_migrations")
    assert {c["name"] for c in inspector.get_columns("import_batches")} >= {"uploaded_by_label", "auth_method", "auth_subject"}
    assert {i["name"] for i in inspector.get_indexes("raw_import_rows")} >= {"ix_raw_import_rows_batch_id"}
    assert {i["name"] for i in inspector.get_indexes("import_batches")} >= {"ix_import_batches_account_created_at"}
    with e.connect() as conn:
        assert [r.version for r in conn.execute(select(schema_migrations.c.version).order_by(schema_migrations.c.version))] == [1, 2, 3, 4]
        assert conn.execute(select(monthly_targets.c.id)).first() is not None
    assert {"app_users", "user_account_access", "auth_sessions", "oidc_login_states"} <= set(inspector.get_table_names())


def test_migrations_adopt_existing_sqlite_and_preserve_data():
    e = engine()
    with e.begin() as conn:
        conn.execute(text("""
            create table import_batches (
                id integer primary key,
                file_sha varchar(64) not null,
                filename varchar(255) not null,
                account varchar(64) not null,
                inserted integer not null default 0,
                updated integer not null default 0,
                unchanged integer not null default 0,
                rejected integer not null default 0,
                created_at datetime default current_timestamp
            )
        """))
        conn.execute(text("""
            create table raw_import_rows (
                id integer primary key,
                batch_id integer not null,
                row_number integer not null,
                business_key varchar(512) not null,
                raw_json text not null
            )
        """))
        conn.execute(text("insert into import_batches (id, file_sha, filename, account, inserted) values (1, 'abc', 'old.xlsx', 'CHIISTORE', 3)"))
        conn.execute(text("insert into raw_import_rows (id, batch_id, row_number, business_key, raw_json) values (1, 1, 2, 'k', '{}')"))

    init_db(e)
    init_db(e)

    inspector = inspect(e)
    assert {c["name"] for c in inspector.get_columns("import_batches")} >= {"uploaded_by_label", "auth_method", "auth_subject"}
    assert {i["name"] for i in inspector.get_indexes("raw_import_rows")} >= {"ix_raw_import_rows_batch_id"}
    assert inspector.has_table("order_line_versions")
    assert inspector.has_table("monthly_targets")
    with e.connect() as conn:
        old = conn.execute(text("select file_sha, filename, account, inserted from import_batches where id = 1")).mappings().one()
        assert dict(old) == {"file_sha": "abc", "filename": "old.xlsx", "account": "CHIISTORE", "inserted": 3}
        assert [r.version for r in conn.execute(select(schema_migrations.c.version).order_by(schema_migrations.c.version))] == [1, 2, 3, 4]


def test_import_rows_stores_optional_identity_audit():
    e = engine()
    init_db(e)

    result = import_rows(
        e,
        filename="a.xlsx",
        file_bytes=b"a",
        account="CHIISTORE",
        rows=[raw_row()],
        uploaded_by_label="Local Operator",
        auth_method="local",
        auth_subject="operator@example.test",
    )

    with e.connect() as conn:
        batch = conn.execute(select(import_batches).where(import_batches.c.id == result["batch_id"])).mappings().one()
    assert batch["uploaded_by_label"] == "Local Operator"
    assert batch["auth_method"] == "local"
    assert batch["auth_subject"] == "operator@example.test"


def test_migrations_repair_import_batches_only_partial_schema():
    e = engine()
    with e.begin() as conn:
        conn.execute(text("""
            create table import_batches (
                id integer primary key,
                file_sha varchar(64) not null,
                filename varchar(255) not null,
                account varchar(64) not null,
                inserted integer not null default 0,
                updated integer not null default 0,
                unchanged integer not null default 0,
                rejected integer not null default 0,
                created_at datetime default current_timestamp
            )
        """))

    init_db(e)

    inspector = inspect(e)
    assert {"raw_import_rows", "order_line_versions", "monthly_targets"} <= set(inspector.get_table_names())
