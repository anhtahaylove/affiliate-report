from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from sqlalchemy import inspect, select, text

from affiliate_report.api import _runtime_capabilities
from affiliate_report.auth import AuthService, AuthSettings
from affiliate_report.db import (
    accounts,
    get_engine,
    import_batches,
    import_rows,
    init_db,
    monthly_targets,
    order_line_versions,
    saved_report_views,
    user_ui_preferences,
)
from affiliate_report.migrations import schema_migrations
from tests.test_imports import raw_row


def engine():
    return get_engine("sqlite:///:memory:")


def test_init_db_runs_versioned_migrations_and_seeds_targets():
    e = engine()

    init_db(e)
    init_db(e)

    inspector = inspect(e)
    assert inspector.has_table("schema_migrations")
    assert inspector.has_table("device_identity")
    assert inspector.has_table("sync_tombstones")
    assert inspector.has_table("sync_history")
    assert {c["name"] for c in inspector.get_columns("import_batches")} >= {"uploaded_by_label", "auth_method", "auth_subject"}
    assert {c["name"] for c in inspector.get_columns("import_batches")} >= {"sync_id", "source_device_id", "source_created_at"}
    assert {c["name"] for c in inspector.get_columns("monthly_targets")} >= {"sync_id", "source_device_id", "sync_updated_at"}
    assert {i["name"] for i in inspector.get_indexes("raw_import_rows")} >= {"ix_raw_import_rows_batch_id"}
    assert {i["name"] for i in inspector.get_indexes("import_batches")} >= {"ix_import_batches_account_created_at"}
    with e.connect() as conn:
        assert [r.version for r in conn.execute(select(schema_migrations.c.version).order_by(schema_migrations.c.version))] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        assert conn.execute(select(monthly_targets.c.id)).first() is None
        assert conn.execute(select(accounts)).first() is None
    assert {"app_users", "user_account_access", "auth_sessions", "oidc_login_states"} <= set(inspector.get_table_names())
    assert inspector.has_table("accounts")
    assert {c["name"] for c in inspector.get_columns("accounts")} >= {"code", "sync_id", "display_name", "active", "display_order", "created_at", "updated_at"}
    assert {i["name"] for i in inspector.get_indexes("accounts")} >= {"uq_accounts_sync_id"}
    assert {c["name"] for c in inspector.get_columns("order_line_versions")} >= {"product_id", "shop_id", "content_type", "content_id", "order_type", "commission_type", "currency"}
    assert {user_ui_preferences.name, saved_report_views.name} <= set(inspector.get_table_names())
    assert {index["name"] for index in inspector.get_indexes(saved_report_views.name)} >= {
        "ix_saved_views_principal_route",
        "uq_saved_view_default_principal_route",
    }


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
        assert [r.version for r in conn.execute(select(schema_migrations.c.version).order_by(schema_migrations.c.version))] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        assert conn.execute(select(accounts.c.code)).scalar_one() == "CHIISTORE"
        assert conn.execute(select(accounts.c.sync_id)).scalar_one()


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


def test_import_rows_stores_normalized_analytics_fields():
    e = engine()
    init_db(e)
    row = raw_row()
    row.update({
        "product_id": "P1",
        "shop_id": "SHOP1",
        "content_type": "Video",
        "content_id": "C1",
        "order_type": "Affiliate",
        "commission_type": "Standard",
        "currency": "VND",
    })

    import_rows(e, filename="analytics.xlsx", file_bytes=b"analytics", account="CHIISTORE", rows=[row])

    with e.connect() as conn:
        version = conn.execute(select(order_line_versions)).mappings().one()
    assert {
        "product_id": version["product_id"],
        "shop_id": version["shop_id"],
        "content_type": version["content_type"],
        "content_id": version["content_id"],
        "order_type": version["order_type"],
        "commission_type": version["commission_type"],
        "currency": version["currency"],
    } == {
        "product_id": "P1",
        "shop_id": "SHOP1",
        "content_type": "Video",
        "content_id": "C1",
        "order_type": "Affiliate",
        "commission_type": "Standard",
        "currency": "VND",
    }


def test_migration_backfills_analytics_columns_from_raw_json():
    e = engine()
    with e.begin() as conn:
        conn.execute(text("""
            create table order_line_versions (
                id integer primary key,
                business_key varchar(512) not null,
                account varchar(64) not null,
                order_id varchar(128),
                sku_id varchar(128),
                product_name text,
                shop_name text,
                status varchar(32) not null,
                order_date datetime,
                settlement_date datetime,
                gmv bigint not null default 0,
                units_sold integer not null default 0,
                units_refunded integer not null default 0,
                final_received bigint not null default 0,
                estimated_commission bigint not null default 0,
                estimated_shop_ads_commission bigint not null default 0,
                estimated_bonus bigint not null default 0,
                estimated_partner_bonus bigint not null default 0,
                estimated_revenue_share bigint not null default 0,
                normalized_hash varchar(64) not null,
                batch_id integer not null,
                raw_json text not null,
                version integer not null default 1,
                is_current boolean not null default 1,
                created_at datetime default current_timestamp
            )
        """))
        conn.execute(text("""
            insert into order_line_versions (
                id, business_key, account, order_id, sku_id, status, normalized_hash, batch_id, raw_json
            ) values (
                1, 'k', 'CHIISTORE', 'O1', 'S1', 'settled', 'hash', 1,
                '{"ID sản phẩm":"P1","Mã cửa hàng":"SHOP1","Loại nội dung":"Video","Id nội dung":"C1","Loại đơn hàng":"Affiliate","Loại hoa hồng":"Standard","Đơn vị tiền tệ":"VND"}'
            )
        """))

    init_db(e)

    with e.connect() as conn:
        version = conn.execute(select(order_line_versions)).mappings().one()
    assert version["product_id"] == "P1"
    assert version["shop_id"] == "SHOP1"
    assert version["content_type"] == "Video"
    assert version["content_id"] == "C1"
    assert version["order_type"] == "Affiliate"
    assert version["commission_type"] == "Standard"
    assert version["currency"] == "VND"
    # Migration 8 chạy sau 0005 nên backfill vẫn lấy được dữ liệu, rồi cột mới bị ghi rỗng.
    # Cột khai báo NOT NULL ở database cũ, nên đây là phép thử migration 8 trên đúng ràng buộc đó.
    assert version["raw_json"] == ""


def test_migration_renames_target_commission_and_keeps_existing_values():
    e = engine()
    with e.begin() as conn:
        conn.execute(text("""
            create table monthly_targets (
                id integer primary key,
                account varchar(64) not null,
                month date not null,
                target_commission bigint not null
            )
        """))
        conn.execute(text("insert into monthly_targets (id, account, month, target_commission) values (1, 'CHIISTORE', '2026-03-01', 250000)"))

    init_db(e)
    init_db(e)  # chạy lại phải không đổi gì thêm

    columns = {column["name"] for column in inspect(e).get_columns("monthly_targets")}
    assert "daily_target_commission" in columns
    assert "target_commission" not in columns
    with e.connect() as conn:
        kept = conn.execute(select(monthly_targets.c.account, monthly_targets.c.daily_target_commission)).all()
    assert kept == [("CHIISTORE", 250000)]


@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_URL"), reason="POSTGRES_TEST_URL not set")
def test_migration_renames_target_commission_on_postgres_too():
    e = get_engine(os.environ["POSTGRES_TEST_URL"])
    with e.begin() as conn:
        conn.execute(text("drop schema public cascade; create schema public"))
        conn.execute(text("""
            create table monthly_targets (
                id serial primary key,
                account varchar(64) not null,
                month date not null,
                target_commission bigint not null
            )
        """))
        conn.execute(text("insert into monthly_targets (account, month, target_commission) values ('CHIISTORE', '2026-03-01', 250000)"))

    try:
        init_db(e)

        columns = {column["name"] for column in inspect(e).get_columns("monthly_targets")}
        assert "daily_target_commission" in columns
        assert "target_commission" not in columns
        with e.connect() as conn:
            assert conn.execute(select(monthly_targets.c.daily_target_commission)).scalar_one() == 250000
    finally:
        # Postgres trong CI dùng chung cho mọi test; migration 0005 seed accounts từ
        # monthly_targets, nên không dọn là test migrate chạy sau sẽ thấy target không rỗng.
        with e.begin() as conn:
            conn.execute(text(
                "TRUNCATE TABLE auth_sessions, oidc_login_states, user_account_access, monthly_targets, "
                "order_line_versions, raw_import_rows, import_batches, app_users, accounts RESTART IDENTITY CASCADE"
            ))
        e.dispose()


@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_URL"), reason="POSTGRES_TEST_URL not set")
def test_postgres_runtime_capabilities_disable_local_settings():
    e = get_engine(os.environ["POSTGRES_TEST_URL"])
    try:
        with e.begin() as conn:
            conn.execute(text("drop schema public cascade; create schema public"))
        init_db(e)
        auth = AuthService(
            e,
            AuthSettings(
                mode="oidc",
                oidc_client_id="client",
                oidc_issuer="https://idp.example.test",
                oidc_redirect_uri="https://app.example.test/auth/callback",
                bootstrap_owner_email="owner@example.test",
                allowed_emails=("owner@example.test",),
            ),
        )
        app = FastAPI()
        app.state.engine = e
        app.state.auth = auth

        capabilities = _runtime_capabilities(app)

        assert capabilities["database_backend"] == "postgresql"
        assert capabilities["data_admin"]["available"] is False
        assert "PostgreSQL" in capabilities["data_admin"]["reason"]
        assert capabilities["update_check"]["available"] is False
        assert capabilities["update_install"]["available"] is False
    finally:
        e.dispose()


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
