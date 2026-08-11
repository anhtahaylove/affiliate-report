from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.engine import Engine

from .db import (
    accounts,
    app_users,
    get_engine,
    auth_sessions,
    import_batches,
    init_db,
    monthly_targets,
    oidc_login_states,
    order_line_versions,
    raw_import_rows,
    saved_report_views,
    user_account_access,
    user_ui_preferences,
)

RESET_CONFIRMATION_PHRASE = "XOA DU LIEU"
RESTORE_CONFIRMATION_PHRASE = "KHOI PHUC DU LIEU"
RESET_TABLES = (raw_import_rows, order_line_versions, import_batches)
PREFERENCE_TABLES = (user_ui_preferences, saved_report_views)
RESTORE_DELETE_TABLES = (
    saved_report_views,
    user_ui_preferences,
    raw_import_rows,
    order_line_versions,
    import_batches,
    monthly_targets,
    accounts,
)
BUSINESS_TABLES = (accounts, monthly_targets, import_batches, raw_import_rows, order_line_versions)
RESTORE_TABLES = (*BUSINESS_TABLES, *PREFERENCE_TABLES)
AUTH_TABLES = (app_users, user_account_access, auth_sessions, oidc_login_states)
REQUIRED_TABLES = (*RESTORE_TABLES, *AUTH_TABLES)


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
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    freed = _vacuum(engine, db_path)
    return {
        "backup_path": str(backup_path),
        "deleted_counts": counts,
        "targets_preserved": True,
        "freed_bytes": freed,
    }


def _vacuum(engine: Engine, db_path: Path) -> int:
    """Xoá dữ liệu chỉ đánh dấu trang là trống, file vẫn giữ nguyên kích thước — một database đã
    reset có thể còn nằm ì hàng chục MB. VACUUM ngay tại chỗ sinh ra chỗ trống, để người dùng
    không phải biết tới khái niệm này."""
    before = db_path.stat().st_size
    engine.dispose()  # VACUUM không chạy được khi còn transaction/connection đang mở
    with engine.connect() as conn:
        conn.exec_driver_sql("VACUUM")
    return max(before - db_path.stat().st_size, 0)


def backup_sqlite_before_change(engine: Engine, label: str) -> str | None:
    """Sao lưu đã kiểm tra trước một thao tác phá huỷ. Trả None khi không phải SQLite cục bộ
    (PostgreSQL dùng chung tự lo sao lưu ở tầng hạ tầng)."""
    try:
        db_path = sqlite_file_path(engine)
    except ValueError:
        return None
    backup_path = _backup_path(db_path, label)
    _backup_sqlite(db_path, backup_path)
    _check_backup(backup_path)
    return str(backup_path)


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
    usable_path = _usable_backup_path(backup_path)
    try:
        _check_required_schema(usable_path)
        return _backup_meta(backup_path) | {"valid": True, "counts": _counts(usable_path)}
    finally:
        _unlink_temp_backup(usable_path, backup_path)


def restore_sqlite_business_backup(engine: Engine, backup_id: str, confirmation: str) -> dict[str, object]:
    if confirmation != RESTORE_CONFIRMATION_PHRASE:
        raise ValueError(f"confirmation must be {RESTORE_CONFIRMATION_PHRASE!r}")
    db_path = sqlite_file_path(engine)
    backup_path = _resolve_backup_id(db_path, backup_id)
    _check_backup(backup_path)
    usable_path = _usable_backup_path(backup_path)
    _check_required_schema(usable_path)
    safety_backup_path = _backup_path(db_path, "restore-safety", protect=backup_path)

    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            _backup_sqlite(db_path, safety_backup_path)
            _check_backup(safety_backup_path)
            _check_required_schema(safety_backup_path)
            _replace_business_tables(conn, usable_path)
            restored_counts = _table_counts(conn, RESTORE_TABLES)
            conn.commit()
            _detach_restore_backup(conn)
        except Exception:
            conn.rollback()
            _detach_restore_backup(conn)
            raise
        finally:
            _unlink_temp_backup(usable_path, backup_path)
    return {
        "restored_counts": restored_counts,
        "safety_backup_path": str(safety_backup_path),
        "freed_bytes": _vacuum(engine, db_path),
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


BACKUP_RETENTION = 3


def _prune_backups(db_path: Path, keep: int, protect: Path | None = None) -> list[str]:
    """Mỗi thao tác nguy hiểm tạo một bản sao lưu đầy đủ. Không dọn thì thư mục phình mãi —
    một database 25 MB nhân với vài chục lần xoá tài khoản là hàng trăm MB nằm chết."""
    backup_dir = _backup_dir(db_path)
    if not backup_dir.exists():
        return []
    keeper = protect.resolve() if protect else None
    candidates = sorted(
        (path for path in backup_dir.iterdir() if _is_candidate_backup(db_path, path)),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed: list[str] = []
    for path in candidates[max(keep, 0):]:
        if keeper is not None and path.resolve() == keeper:
            continue  # không bao giờ xoá bản đang được khôi phục
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            pass
    return removed


def _backup_path(db_path: Path, label: str, protect: Path | None = None) -> Path:
    backup_dir = _backup_dir(db_path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    # Dọn trước khi tạo: giữ lại chỗ cho đúng bản sắp ghi để tổng luôn bằng BACKUP_RETENTION.
    _prune_backups(db_path, BACKUP_RETENTION - 1, protect)
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
        usable_path = _usable_backup_path(path)
        try:
            _check_required_schema(usable_path)
            return _backup_meta(path) | {"valid": True, "counts": _counts(usable_path)}
        finally:
            _unlink_temp_backup(usable_path, path)
    except (RuntimeError, ValueError) as exc:
        return _backup_meta(path) | {
            "valid": False,
            "counts": {"business": {}, "ui": {}, "auth": {}},
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
        ui = {table.name: _sqlite_count(conn, table.name) for table in PREFERENCE_TABLES}
        auth = {table.name: _sqlite_count(conn, table.name) for table in AUTH_TABLES}
    finally:
        conn.close()
    return {"business": business, "ui": ui, "auth": auth}


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
            missing = [column for column in expected if column not in actual]
            if missing:
                raise ValueError(f"Backup schema for {table.name} is missing columns: {', '.join(missing)}.")
    finally:
        conn.close()


def _replace_business_tables(conn, backup_path: Path) -> None:
    conn.exec_driver_sql("ATTACH DATABASE ? AS restore_backup", (str(backup_path),)).close()
    for table in RESTORE_DELETE_TABLES:
        conn.exec_driver_sql(f'DELETE FROM "{table.name}"').close()
    for table in RESTORE_TABLES:
        if table in PREFERENCE_TABLES:
            _restore_preference_table(conn, table)
            continue
        columns = [column.name for column in table.columns]
        quoted = ", ".join(f'"{column}"' for column in columns)
        conn.exec_driver_sql(
            f'INSERT INTO "{table.name}" ({quoted}) '
            f'SELECT {quoted} FROM restore_backup."{table.name}"'
        ).close()


def _restore_preference_table(conn, table) -> None:
    """Khôi phục UI state theo OIDC identity ổn định, không theo numeric user id.

    SQLite có thể tái sử dụng ``app_users.id`` sau khi xoá user. Nếu copy trực tiếp
    ``app_user_id``/``principal_key=user:<id>`` từ backup, preferences của identity cũ
    có thể bị gán cho identity mới. Join issuer+subject tránh rò rỉ chéo identity; local
    owner là principal ảo duy nhất nên được giữ nguyên.
    """
    columns = [column.name for column in table.columns]
    quoted = ", ".join(f'"{column}"' for column in columns)
    selected = []
    for column in columns:
        if column == "app_user_id":
            selected.append('current_user."id" AS "app_user_id"')
        elif column == "principal_key":
            selected.append(
                "CASE WHEN source.app_user_id IS NULL "
                "THEN 'local:local-owner' "
                "ELSE 'user:' || current_user.id END AS \"principal_key\""
            )
        else:
            selected.append(f'source."{column}"')
    projection = ", ".join(selected)
    conn.exec_driver_sql(
        f'INSERT INTO "{table.name}" ({quoted}) '
        f'SELECT {projection} FROM restore_backup."{table.name}" AS source '
        'LEFT JOIN restore_backup."app_users" AS backup_user '
        'ON backup_user.id = source.app_user_id '
        'LEFT JOIN main."app_users" AS current_user '
        'ON current_user.issuer = backup_user.issuer '
        'AND current_user.subject = backup_user.subject '
        "WHERE (source.app_user_id IS NULL AND source.principal_key = 'local:local-owner') "
        'OR current_user.id IS NOT NULL'
    ).close()


def _usable_backup_path(backup_path: Path) -> Path:
    try:
        _check_required_schema(backup_path)
        return backup_path
    except ValueError:
        migrated = backup_path.with_name(backup_path.name + ".migrated.tmp")
        migrated.unlink(missing_ok=True)
        engine = None
        try:
            _backup_sqlite(backup_path, migrated)
            engine = get_engine(f"sqlite:///{migrated.as_posix()}")
            init_db(engine)
            _check_backup(migrated)
            _check_required_schema(migrated)
        except Exception as exc:
            if engine is not None:
                engine.dispose()
                engine = None
            migrated.unlink(missing_ok=True)
            raise ValueError(f"Backup schema is not restorable: {exc}") from exc
        finally:
            if engine is not None:
                engine.dispose()
        return migrated


def _unlink_temp_backup(path: Path, original: Path) -> None:
    if path != original:
        path.unlink(missing_ok=True)


def _detach_restore_backup(conn) -> None:
    try:
        conn.exec_driver_sql("DETACH DATABASE restore_backup").close()
    except Exception:
        pass
