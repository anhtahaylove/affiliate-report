from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from affiliate_report.accounts import (
    active_account_codes,
    can_hard_delete_accounts,
    create_account,
    delete_account,
    delete_account_preview,
    list_accounts,
    update_account,
)
from affiliate_report.db import accounts, get_engine, import_batches, import_rows, init_db, monthly_targets, order_line_versions, raw_import_rows
from tests.test_imports import raw_row


def file_engine(tmp_path: Path):
    db_path = tmp_path / "accounts.db"
    engine = get_engine(f"sqlite:///{db_path.as_posix()}")
    init_db(engine)
    return engine, db_path


def test_account_helpers_list_update_archive_and_validate_display_name(tmp_path):
    engine, _ = file_engine(tmp_path)

    assert create_account(engine, "a", display_name="One-letter")["code"] == "A"
    created = create_account(engine, "shop_1", display_name="Shop 1")
    create_account(engine, "shop_2", display_name="Shop 2")
    updated = update_account(engine, "SHOP_2", display_name="Second", active=False, display_order=5)

    assert created["code"] == "SHOP_1"
    assert updated["display_name"] == "Second"
    assert active_account_codes(engine) == ("A", "SHOP_1")
    assert [row["code"] for row in list_accounts(engine, include_inactive=True)] == ["SHOP_2", "A", "SHOP_1"]
    with pytest.raises(ValueError, match="A-Z"):
        create_account(engine, "BAD CODE")
    with pytest.raises(ValueError, match="A-Z"):
        create_account(engine, "ĐẸP")
    with pytest.raises(ValueError, match="128"):
        create_account(engine, "TOO_LONG_NAME", display_name="x" * 129)



def test_import_rows_creates_account_registry_and_rejects_reserved_all(tmp_path):
    engine, _ = file_engine(tmp_path)

    import_rows(engine, filename="one.xlsx", file_bytes=b"one", account="a", rows=[raw_row(order="OA", account="A")])
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="newshop", rows=[raw_row(account="NEWSHOP")])

    assert active_account_codes(engine) == ("A", "NEWSHOP")
    with pytest.raises(ValueError, match="A-Z"):
        import_rows(engine, filename="bad.xlsx", file_bytes=b"bad", account="bad code", rows=[raw_row(account="BAD CODE")])
    with pytest.raises(ValueError, match="ALL"):
        import_rows(engine, filename="all.xlsx", file_bytes=b"all", account="ALL", rows=[raw_row(account="ALL")])



def test_sqlite_hard_delete_removes_history_after_verified_backup(tmp_path):
    engine, db_path = file_engine(tmp_path)
    create_account(engine, "TESTACC")
    with engine.begin() as conn:
        conn.execute(monthly_targets.insert().values(account="TESTACC", month=date(2026, 3, 1), daily_target_commission=123))
    import_rows(engine, filename="a.xlsx", file_bytes=b"a", account="TESTACC", rows=[raw_row(account="TESTACC")])

    preview = delete_account_preview(engine, "TESTACC")
    assert preview["can_hard_delete"] is True
    assert preview["dependency_counts"].items() >= {
        "raw_import_rows": 1,
        "import_batches": 1,
        "order_line_versions": 1,
        "monthly_targets": 1,
    }.items()

    result = delete_account(engine, "TESTACC", hard=True)

    assert result["hard_deleted"] is True
    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    with sqlite3.connect(str(backup_path)) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
    with engine.connect() as conn:
        assert conn.execute(select(accounts).where(accounts.c.code == "TESTACC")).first() is None
        assert conn.execute(select(import_batches).where(import_batches.c.account == "TESTACC")).first() is None
        assert conn.execute(select(raw_import_rows)).first() is None
        assert conn.execute(select(order_line_versions).where(order_line_versions.c.account == "TESTACC")).first() is None
        assert conn.execute(select(monthly_targets).where(monthly_targets.c.account == "TESTACC")).first() is None



def test_hard_delete_on_non_sqlite_path_archives(monkeypatch, tmp_path):
    engine, _ = file_engine(tmp_path)
    create_account(engine, "PGACC")
    monkeypatch.setattr(engine.dialect, "name", "postgresql")

    result = delete_account(engine, "PGACC", hard=True)

    assert result["archived"] is True
    assert result["hard_deleted"] is False
    assert result["account"]["active"] is False


def test_in_memory_sqlite_is_not_advertised_as_hard_delete():
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    create_account(engine, "MEMORY")

    assert can_hard_delete_accounts(engine) is False
    assert delete_account_preview(engine, "MEMORY")["can_hard_delete"] is False
    result = delete_account(engine, "MEMORY", hard=True)

    assert result["archived"] is True
    assert result["hard_deleted"] is False
