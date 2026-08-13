from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affiliate_report.db import (
    accounts,
    app_users,
    get_engine,
    import_batches,
    monthly_targets,
    order_line_versions,
    raw_import_rows,
    user_account_access,
)
from affiliate_report.migrations import apply_migrations

COPY_TABLES = (
    accounts,
    import_batches,
    raw_import_rows,
    order_line_versions,
    monthly_targets,
    app_users,
    user_account_access,
)
EXCLUDED_TABLES = ("auth_sessions", "oidc_login_states")


def sqlite_url(value: str) -> str:
    if value.startswith("sqlite://"):
        return value
    return "sqlite:///" + str(Path(value).expanduser().resolve()).replace("\\", "/")


def mask_secret(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted>"
    if parts.password is None:
        return value
    username = parts.username or ""
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{username}:***@{host}{port}" if username else f"***@{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def assert_postgres(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Target database must be PostgreSQL.")


def count_rows(engine: Engine, table_name: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {quote_ident(engine, table_name)}")).scalar_one())


def quote_ident(engine: Engine, name: str) -> str:
    return engine.dialect.identifier_preparer.quote(name)


def require_empty_target(engine: Engine) -> None:
    non_empty = [table.name for table in COPY_TABLES if count_rows(engine, table.name)]
    non_empty.extend(table_name for table_name in EXCLUDED_TABLES if count_rows(engine, table_name))
    if non_empty:
        raise RuntimeError("Target tables must be empty before migration: " + ", ".join(non_empty))


def rows_from(engine: Engine, table: Any) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(table).order_by(*table.primary_key.columns)).mappings()]


def copy_rows(source: Engine, target: Engine) -> dict[str, int]:
    counts: dict[str, int] = {}
    with target.begin() as conn:
        for table in COPY_TABLES:
            rows = rows_from(source, table)
            counts[table.name] = len(rows)
            if rows:
                conn.execute(table.insert(), rows)
        reset_postgres_sequences(conn, target)
        verify_counts(conn, target, counts)
    return counts


def reset_postgres_sequences(conn: Connection, engine: Engine) -> None:
    for table in COPY_TABLES:
        pk = [col for col in table.primary_key.columns if col.name == "id"]
        if not pk:
            continue
        table_sql = quote_ident(engine, table.name)
        seq = conn.execute(text("SELECT pg_get_serial_sequence(:table_name, 'id')"), {"table_name": table.name}).scalar()
        if not seq:
            continue
        conn.execute(
            text(
                f"SELECT setval(CAST(:seq AS regclass), "
                f"COALESCE((SELECT MAX(id) FROM {table_sql}), 1), "
                f"(SELECT COUNT(*) > 0 FROM {table_sql}))"
            ),
            {"seq": seq},
        )


def verify_counts(conn: Connection, target: Engine, expected: dict[str, int]) -> None:
    mismatches = []
    for table in COPY_TABLES:
        src = expected[table.name]
        dst = int(conn.execute(text(f"SELECT COUNT(*) FROM {quote_ident(target, table.name)}")).scalar_one())
        if src != dst:
            mismatches.append(f"{table.name}: source={src} target={dst}")
    for table_name in EXCLUDED_TABLES:
        if conn.execute(text(f"SELECT COUNT(*) FROM {quote_ident(target, table_name)}")).scalar_one() != 0:
            mismatches.append(f"{table_name}: expected target=0")
    if mismatches:
        raise RuntimeError("Count verification failed: " + "; ".join(mismatches))


def migrate(source_value: str, target_value: str) -> dict[str, int]:
    source = get_engine(sqlite_url(source_value))
    target = get_engine(target_value)
    assert_postgres(target)
    apply_migrations(source)
    apply_migrations(target)
    require_empty_target(target)
    counts = copy_rows(source, target)
    return counts


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate TikTok affiliate data from SQLite to an empty PostgreSQL database.")
    parser.add_argument("--source", required=True, help="SQLite path or sqlite:/// URL")
    parser.add_argument("--target", required=True, help="PostgreSQL URL")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        counts = migrate(args.source, args.target)
    except (RuntimeError, SQLAlchemyError, ValueError) as exc:
        msg = str(exc)
        msg = msg.replace(args.source, mask_secret(args.source)).replace(args.target, mask_secret(args.target))
        msg = re.sub(r"(postgres(?:ql)?(?:\+psycopg)?://[^\s'\"]+)", lambda m: mask_secret(m.group(1)), msg)
        print(f"Migration failed: {msg}", file=sys.stderr)
        return 1
    print("Migration complete: " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
