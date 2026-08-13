from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select, text

from scripts.migrate_sqlite_to_postgres import mask_secret, migrate
from tests.test_imports import raw_row
from affiliate_report.db import (
    accounts,
    app_users,
    get_engine,
    import_batches,
    import_rows,
    init_db,
    monthly_targets,
    order_line_versions,
    user_account_access,
)


def build_source(path: Path):
    engine = get_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="CHIISTORE", rows=[raw_row()])
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="CHIISTORE", month=date(2026, 3, 1), daily_target_commission=123))
        user_id = conn.execute(app_users.insert().values(
            issuer="issuer", subject="subject", email="owner@example.test", display_name="Owner", role="owner", active=True,
        )).inserted_primary_key[0]
        conn.execute(user_account_access.insert().values(user_id=user_id, account="CHIISTORE"))
        conn.execute(text("insert into auth_sessions (token_hash, user_id, csrf_hash, expires_at) values ('tok', :uid, 'csrf', '2099-01-01')"), {"uid": user_id})
        conn.execute(text("insert into oidc_login_states (state_hash, code_verifier, nonce, expires_at) values ('state', 'verifier', 'nonce', '2099-01-01')"))
    return engine


def downgrade_source_to_v4(engine) -> None:
    analytics_columns = (
        "product_id",
        "shop_id",
        "content_type",
        "content_id",
        "order_type",
        "commission_type",
        "currency",
    )
    with engine.begin() as conn:
        for index in (
            "ix_order_line_versions_product_id",
            "ix_order_line_versions_shop_id",
            "ix_order_line_versions_content_id",
        ):
            conn.execute(text(f"DROP INDEX IF EXISTS {index}"))
        for column in analytics_columns:
            conn.execute(text(f"ALTER TABLE order_line_versions DROP COLUMN {column}"))
        conn.execute(text("DROP TABLE accounts"))
        # Database v4 thật có raw_json đầy đủ — bản v4 này lại dựng từ import_rows của mã hiện
        # tại, vốn để cột đó rỗng từ migration 8. Trả nội dung vào cho giống hàng thật, nếu
        # không thì migration 0005 chẳng có gì để backfill và phép thử mất ý nghĩa.
        conn.execute(text("""
            UPDATE order_line_versions SET raw_json = (
                SELECT r.raw_json FROM raw_import_rows r
                WHERE r.business_key = order_line_versions.business_key LIMIT 1)
        """))
        # Bỏ cả 8 để đường nâng cấp chạy đúng thứ tự thật: 0005 backfill trước, 8 dọn sau.
        conn.execute(text("DELETE FROM schema_migrations WHERE version IN (5, 8)"))


def test_mask_secret_hides_password():
    assert mask_secret("postgresql://user:secret@localhost:5432/db") == "postgresql://user:***@localhost:5432/db"


def test_cli_errors_do_not_print_postgres_password(tmp_path):
    script = Path("scripts/migrate_sqlite_to_postgres.py")
    result = subprocess.run(
        [sys.executable, str(script), "--source", str(tmp_path / "missing.db"), "--target", "postgresql://user:super-secret@localhost:1/db?connect_timeout=1"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "super-secret" not in result.stderr


@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_URL"), reason="POSTGRES_TEST_URL not set")
def test_migrate_v4_sqlite_to_empty_postgres(tmp_path):
    source = build_source(tmp_path / "source.db")
    downgrade_source_to_v4(source)
    target_url = os.environ["POSTGRES_TEST_URL"]
    target = get_engine(target_url)

    try:
        counts = migrate(str(tmp_path / "source.db"), target_url)

        assert counts["import_batches"] == 1
        assert counts["accounts"] == 1
        assert counts["raw_import_rows"] == 1
        assert counts["order_line_versions"] == 1
        assert counts["app_users"] == 1
        assert counts["user_account_access"] == 1
        with target.connect() as conn:
            assert conn.execute(select(accounts.c.code)).scalar_one() == "CHIISTORE"
            migrated = conn.execute(select(
                order_line_versions.c.business_key,
                order_line_versions.c.product_id,
                order_line_versions.c.shop_id,
                order_line_versions.c.content_type,
                order_line_versions.c.content_id,
                order_line_versions.c.currency,
            )).one()
            assert migrated == (migrated.business_key, "P1", "SHOP1", "Video", "C1", "VND")
            assert conn.execute(text("select count(*) from auth_sessions")).scalar_one() == 0
            assert conn.execute(text("select count(*) from oidc_login_states")).scalar_one() == 0
            next_id = conn.execute(import_batches.insert().values(file_sha="b" * 64, filename="b.xlsx", account="CHIISTORE")).inserted_primary_key[0]
        assert next_id > 1

        changed = import_rows(
            target,
            filename="changed.xlsx",
            file_bytes=b"changed",
            account="CHIISTORE",
            rows=[raw_row(gmv="200.000")],
        )
        assert changed["updated"] == 1
        with target.connect() as conn:
            versions = conn.execute(
                select(order_line_versions.c.version, order_line_versions.c.is_current)
                .order_by(order_line_versions.c.version)
            ).all()
        assert versions == [(1, False), (2, True)]
    finally:
        with target.begin() as conn:
            conn.execute(text("TRUNCATE TABLE auth_sessions, oidc_login_states, user_account_access, monthly_targets, order_line_versions, raw_import_rows, import_batches, app_users, accounts RESTART IDENTITY CASCADE"))
