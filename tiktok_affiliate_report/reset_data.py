from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.engine import Engine

from .db import (
    DEFAULT_MONTHLY_TARGETS,
    app_users,
    auth_sessions,
    import_batches,
    monthly_targets,
    oidc_login_states,
    order_line_versions,
    raw_import_rows,
    user_account_access,
)

RESET_CONFIRMATION_PHRASE = "XOA DU LIEU"
RESTORE_CONFIRMATION_PHRASE = "KHOI PHUC DU LIEU"
RESET_TABLES = (raw_import_rows, order_line_versions, import_batches, monthly_targets)
BUSINESS_TABLES = (import_batches, raw_import_rows, order_line_versions, monthly_targets)
AUTH_TABLES = (app_users, user_account_access, auth_sessions, oidc_login_states)
REQUIRED_TABLES = (*BUSINESS_TABLES, *AUTH_TABLES)


def reset_sqlite_business_data(engine: Engine) -> dict[str, object]:
    db_path = sqlite_file_path(engine)
    backup_path = _backup_path(db_path, "reset")

    counts: dict[str, int] = {}
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            _backup_sqlite(db_path, backup_path)
            _check_backup(backup_path)

            for table in RESET_TABLES:
                counts[table.name] = conn.execute(delete(table)).rowcount or 0
            for month, amount in DEFAULT_MONTHLY_TARGETS.items():
                conn.execute(monthly_targets.insert().values(account="ALL", month=month, target_commission=amount))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "backup_path": str(backup_path),
        "deleted_counts": counts,
        "default_targets_restored": len(DEFAULT_MONTHLY_TARGETS),
    }


def list_sqlite_backups(engine: Engine) -> list[dict[str, object]]:
    db_path = sqlite_file_path(engine)
    backup_dir = _backup_dir(db_path)
    if not backup_dir.exists():
        return []
    paths = [path for path in backup_dir.iterdir() if _is_candidate_backup(db_path, path)]
    return [_backup_item(path) for path in sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)]


def preview_sqlite_backup(engine: Engine, backup_id: str) -> dict[str, object]:
    db_path = sqlite_file_path(engine)
    backup_path = _resolve_backup_id(db_path, backup_id)
    _check_backup(backup_path)
    _check_required_schema(backup_path)
    return _backup_meta(backup_path) | {"valid": True, "counts": _counts(backup_path)}


def restore_sqlite_business_backup(engine: Engine, backup_id: str, confirmation: str) -> dict[str, object]:
    if confirmation != RESTORE_CONFIRMATION_PHRASE:
        raise ValueError(f"confirmation must be {RESTORE_CONFIRMATION_PHRASE!r}")
    db_path = sqlite_file_path(engine)
    backup_path = _resolve_backup_id(db_path, backup_id)
    _check_backup(backup_path)
    _check_required_schema(backup_path)
    safety_backup_path = _backup_path(db_path, "restore-safety")

    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            _backup_sqlite(db_path, safety_backup_path)
            _check_backup(safety_backup_path)
            _check_required_schema(safety_backup_path)
            _replace_business_tables(conn, backup_path)
            restored_counts = _table_counts(conn, BUSINESS_TABLES)
            conn.commit()
            _detach_restore_backup(conn)
        except Exception:
            conn.rollback()
            _detach_restore_backup(conn)
            raise
    return {
        "restored_counts": restored_counts,
        "safety_backup_path": str(safety_backup_path),
    }


def sqlite_file_path(engine: Engine) -> Path:
    if engine.dialect.name != "sqlite":
        raise ValueError("Restore/reset data is only available for local SQLite databases.")
    query = dict(engine.url.query)
    if query.get("cache") == "shared" or query.get("mode") == "memory":
        raise ValueError("Restore/reset data is disabled for shared SQLite mode.")
    database = engine.url.database
    if not database or database == ":memory:":
        raise ValueError("Restore/reset data requires a file-backed local SQLite database.")
    path = Path(database).expanduser().resolve()
    if not path.exists():
        raise ValueError("SQLite database file does not exist.")
    return path


def _backup_dir(db_path: Path) -> Path:
    return db_path.parent / "backups"


def _backup_path(db_path: Path, label: str) -> Path:
    backup_dir = _backup_dir(db_path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    suffix = db_path.suffix or ".db"
    for _ in range(100):
        path = backup_dir / f"{db_path.stem}-{label}-{stamp}-{uuid4().hex[:8]}{suffix}"
        if not path.exists():
            return path
    raise RuntimeError("Could not allocate a unique backup path.")


def _backup_sqlite(db_path: Path, backup_path: Path) -> None:
    source = sqlite3.connect(str(db_path))
    try:
        target = sqlite3.connect(str(backup_path))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _check_backup(backup_path: Path) -> None:
    try:
        conn = sqlite3.connect(str(backup_path))
        try:
            result = conn.execute("PRAGMA quick_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("SQLite backup quick_check failed; operation aborted.") from exc
    if result != ("ok",):
        raise RuntimeError("SQLite backup quick_check failed; operation aborted.")


def _resolve_backup_id(db_path: Path, backup_id: str) -> Path:
    if not backup_id or Path(backup_id).name != backup_id:
        raise ValueError("Backup filename is invalid.")
    path = _backup_dir(db_path) / backup_id
    if not _is_candidate_backup(db_path, path):
        raise ValueError("Backup file is not available.")
    if path.resolve().parent != _backup_dir(db_path).resolve():
        raise ValueError("Backup file is outside the backup directory.")
    return path


def _is_candidate_backup(db_path: Path, path: Path) -> bool:
    return (
        path.exists()
        and path.is_file()
        and not path.is_symlink()
        and path.parent.resolve() == _backup_dir(db_path).resolve()
        and path.name.startswith(f"{db_path.stem}-")
        and path.suffix == (db_path.suffix or ".db")
    )


def _backup_item(path: Path) -> dict[str, object]:
    try:
        _check_backup(path)
        _check_required_schema(path)
        return _backup_meta(path) | {"valid": True, "counts": _counts(path)}
    except (RuntimeError, ValueError) as exc:
        return _backup_meta(path) | {
            "valid": False,
            "counts": {"business": {}, "auth": {}},
            "error": str(exc),
        }


def _backup_meta(path: Path) -> dict[str, object]:
    stat = path.stat()
    created_at = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
    return {
        "id": path.name,
        "filename": path.name,
        "created_at": created_at,
        "size_bytes": stat.st_size,
        "timestamp": created_at,
        "size": stat.st_size,
    }


def _counts(path: Path) -> dict[str, dict[str, int]]:
    conn = sqlite3.connect(str(path))
    try:
        business = {table.name: _sqlite_count(conn, table.name) for table in BUSINESS_TABLES}
        auth = {table.name: _sqlite_count(conn, table.name) for table in AUTH_TABLES}
    finally:
        conn.close()
    return {"business": business, "auth": auth}


def _sqlite_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _table_counts(conn, tables) -> dict[str, int]:
    return {table.name: int(conn.exec_driver_sql(f'SELECT COUNT(*) FROM "{table.name}"').scalar_one()) for table in tables}


def _check_required_schema(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        for table in REQUIRED_TABLES:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table.name,)).fetchone()
            if not row:
                raise ValueError(f"Backup schema is missing table {table.name}.")
            actual = [col[1] for col in conn.execute(f'PRAGMA table_info("{table.name}")')]
            expected = [column.name for column in table.columns]
            if actual != expected:
                raise ValueError(f"Backup schema for {table.name} does not match the app schema.")
    finally:
        conn.close()


def _replace_business_tables(conn, backup_path: Path) -> None:
    conn.exec_driver_sql("ATTACH DATABASE ? AS restore_backup", (str(backup_path),)).close()
    for table in RESET_TABLES:
        conn.exec_driver_sql(f'DELETE FROM "{table.name}"').close()
    for table in BUSINESS_TABLES:
        columns = [column.name for column in table.columns]
        quoted = ", ".join(f'"{column}"' for column in columns)
        conn.exec_driver_sql(
            f'INSERT INTO "{table.name}" ({quoted}) '
            f'SELECT {quoted} FROM restore_backup."{table.name}"'
        ).close()


def _detach_restore_backup(conn) -> None:
    try:
        conn.exec_driver_sql("DETACH DATABASE restore_backup").close()
    except Exception:
        pass
