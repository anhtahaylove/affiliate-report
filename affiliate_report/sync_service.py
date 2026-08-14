from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import zlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine

from .db import (
    account_sync_id,
    accounts,
    device_identity,
    ensure_device_identity,
    get_engine,
    import_batch_sync_id,
    import_batches,
    monthly_targets,
    order_line_versions,
    raw_import_rows,
    sync_history,
    sync_tombstones,
    target_sync_id,
)
from .parser import DATE_FIELDS, normalize_row
from .reset_data import backup_sqlite_before_change, sqlite_file_path
from .version import APP_VERSION

MAGIC = b"AFFSYNC1"
PACKAGE_SCHEMA = 1
DB_SCHEMA_VERSION = 10
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_PLAINTEXT_BYTES = 400 * 1024 * 1024
PREVIEW_TTL = timedelta(minutes=15)
CONFIRMATION_PHRASE = "DONG BO"
_HEADER_LENGTH_BYTES = 4
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_ACCOUNT_RE = re.compile(r"^[A-Z0-9_-]{1,64}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class SyncError(ValueError):
    pass


class SyncPackageTooLarge(SyncError):
    pass


class SyncPreviewExpired(SyncError):
    pass


@dataclass
class _Preview:
    payload: dict[str, Any]
    package_hash: str
    expires_at: datetime
    summary: dict[str, Any]
    conflicts: list[dict[str, Any]]
    local_state_hash: str


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        text = value.isoformat()
        return text.replace("+00:00", "Z")
    return value


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise SyncError("Gói đồng bộ chứa timestamp không hợp lệ.") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _parse_date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise SyncError("Gói đồng bộ chứa ngày không hợp lệ.") from exc


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_uuid(value: Any, field: str) -> str:
    try:
        parsed = UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise SyncError(f"Gói đồng bộ có {field} không hợp lệ.") from exc
    return str(parsed)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or not 8 <= len(passphrase) <= 256:
        raise SyncError("Mật khẩu đồng bộ phải dài từ 8 đến 256 ký tự.")
    return Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P).derive(
        passphrase.encode("utf-8")
    )


def _bounded_decompress(data: bytes) -> bytes:
    inflater = zlib.decompressobj()
    plain = inflater.decompress(data, MAX_PLAINTEXT_BYTES + 1)
    if len(plain) > MAX_PLAINTEXT_BYTES or inflater.unconsumed_tail:
        raise SyncPackageTooLarge("Dữ liệu giải nén vượt giới hạn an toàn 400 MiB.")
    plain += inflater.flush()
    if len(plain) > MAX_PLAINTEXT_BYTES or not inflater.eof:
        raise SyncPackageTooLarge("Dữ liệu giải nén vượt giới hạn an toàn 400 MiB.")
    return plain


def _encrypt_payload(payload: dict[str, Any], passphrase: str) -> bytes:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    header = {
        "schema": PACKAGE_SCHEMA,
        "kdf": "scrypt",
        "n": _SCRYPT_N,
        "r": _SCRYPT_R,
        "p": _SCRYPT_P,
        "salt": base64.b64encode(salt).decode("ascii"),
        "cipher": "aes-256-gcm",
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    header_bytes = _canonical(header)
    if len(header_bytes) > 65535:
        raise SyncError("Header gói đồng bộ không hợp lệ.")
    prefix = MAGIC + len(header_bytes).to_bytes(_HEADER_LENGTH_BYTES, "big") + header_bytes
    compressed = zlib.compress(_canonical(payload), level=9)
    ciphertext = AESGCM(_derive_key(passphrase, salt)).encrypt(nonce, compressed, prefix)
    package = prefix + ciphertext
    if len(package) > MAX_PACKAGE_BYTES:
        raise SyncPackageTooLarge("Gói đồng bộ vượt giới hạn 100 MiB.")
    return package


def _decrypt_payload(package: bytes, passphrase: str) -> dict[str, Any]:
    if len(package) > MAX_PACKAGE_BYTES:
        raise SyncPackageTooLarge("Gói đồng bộ vượt giới hạn 100 MiB.")
    if len(package) < len(MAGIC) + _HEADER_LENGTH_BYTES + 16 or not package.startswith(MAGIC):
        raise SyncError("Đây không phải gói Affiliate Report .affsync hợp lệ.")
    header_start = len(MAGIC) + _HEADER_LENGTH_BYTES
    header_length = int.from_bytes(package[len(MAGIC):header_start], "big")
    header_end = header_start + header_length
    if header_length <= 0 or header_end + 16 > len(package):
        raise SyncError("Header gói đồng bộ không hợp lệ.")
    prefix = package[:header_end]
    try:
        header = json.loads(package[header_start:header_end])
        if header != {
            "cipher": "aes-256-gcm",
            "kdf": "scrypt",
            "n": _SCRYPT_N,
            "nonce": header.get("nonce"),
            "p": _SCRYPT_P,
            "r": _SCRYPT_R,
            "salt": header.get("salt"),
            "schema": PACKAGE_SCHEMA,
        }:
            raise SyncError("Thuật toán hoặc schema của gói đồng bộ không được hỗ trợ.")
        salt = base64.b64decode(header["salt"], validate=True)
        nonce = base64.b64decode(header["nonce"], validate=True)
        if len(salt) != 16 or len(nonce) != 12:
            raise ValueError
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise SyncError("Header gói đồng bộ không hợp lệ.") from exc
    try:
        compressed = AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, package[header_end:], prefix)
    except InvalidTag as exc:
        raise SyncError("Mật khẩu không đúng hoặc gói đồng bộ đã bị chỉnh sửa.") from exc
    try:
        payload = json.loads(_bounded_decompress(compressed))
    except (json.JSONDecodeError, UnicodeDecodeError, zlib.error) as exc:
        raise SyncError("Nội dung gói đồng bộ bị hỏng.") from exc
    if not isinstance(payload, dict):
        raise SyncError("Nội dung gói đồng bộ không hợp lệ.")
    return payload


class SyncService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._lock = threading.RLock()
        self._previews: dict[str, _Preview] = {}

    def status(self) -> dict[str, Any]:
        self._require_local_sqlite()
        self._purge_previews()
        with self.engine.begin() as conn:
            identity = ensure_device_identity(conn)
            history_count = int(conn.execute(select(func.count()).select_from(sync_history)).scalar_one())
        return {
            "enabled": True,
            "format": "AFFSYNC1",
            "schema": PACKAGE_SCHEMA,
            "confirmation_phrase": CONFIRMATION_PHRASE,
            "preview_ttl_seconds": int(PREVIEW_TTL.total_seconds()),
            "max_package_bytes": MAX_PACKAGE_BYTES,
            "device": {
                "id": identity["device_id"],
                "name": identity["device_name"],
                "platform": identity["platform"],
                "created_at": _iso(identity.get("created_at")),
                "device_id": identity["device_id"],
                "device_name": identity["device_name"],
            },
            "history_count": history_count,
        }

    def export_package(self, passphrase: str) -> tuple[bytes, dict[str, Any]]:
        self._require_local_sqlite()
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                identity = ensure_device_identity(conn)
                data = self._export_data(conn, identity["device_id"])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        package_id = str(uuid4())
        data_hash = hashlib.sha256(_canonical(data)).hexdigest()
        counts = {key: len(value) for key, value in data.items()}
        manifest = {
            "schema": PACKAGE_SCHEMA,
            "app_id": "affiliate-report",
            "app_version": APP_VERSION,
            "db_schema": DB_SCHEMA_VERSION,
            "package_id": package_id,
            "source_device": {
                "device_id": identity["device_id"],
                "device_name": identity["device_name"],
                "platform": identity["platform"],
            },
            "exported_at": _iso(_utcnow()),
            "counts": counts,
            "data_sha256": data_hash,
        }
        package = _encrypt_payload({"manifest": manifest, "data": data}, passphrase)
        package_hash = hashlib.sha256(package).hexdigest()
        summary = {"counts": counts, "filename": self.filename(), "bytes": len(package)}
        with self.engine.begin() as conn:
            conn.execute(sync_history.insert().values(
                package_id=package_id,
                package_hash=package_hash,
                source_device_id=identity["device_id"],
                direction="export",
                summary_json=summary,
            ))
        return package, manifest | {"package_hash": package_hash, "filename": summary["filename"], "bytes": len(package)}

    def preview(self, package: bytes, passphrase: str) -> dict[str, Any]:
        self._require_local_sqlite()
        payload = _decrypt_payload(package, passphrase)
        self._validate_payload(payload)
        package_hash = hashlib.sha256(package).hexdigest()
        manifest = payload["manifest"]
        package_id = manifest["package_id"]
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN")
            try:
                duplicate = conn.execute(select(sync_history.c.package_id).where(sync_history.c.package_id == package_id)).first() is not None
                conflicts, summary = self._compare(conn, payload["data"])
                local_state_hash = self._local_state_hash(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        preview_id = str(uuid4())
        expires_at = _utcnow() + PREVIEW_TTL
        with self._lock:
            self._purge_previews_locked()
            self._previews[preview_id] = _Preview(
                payload,
                package_hash,
                expires_at,
                summary,
                conflicts,
                local_state_hash,
            )
        return {
            "preview_id": preview_id,
            "expires_at": _iso(expires_at),
            "duplicate": duplicate,
            "already_imported": duplicate,
            "package_id": package_id,
            "source_device": manifest["source_device"],
            "exported_at": manifest["exported_at"],
            "counts": manifest["counts"],
            "manifest": manifest,
            "summary": summary,
            "conflicts": conflicts,
        }

    def import_preview(
        self,
        preview_id: str,
        confirmation: str,
        conflict_resolutions: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self._require_local_sqlite()
        if confirmation != CONFIRMATION_PHRASE:
            raise SyncError(f"confirmation must be {CONFIRMATION_PHRASE!r}")
        with self._lock:
            self._purge_previews_locked()
            preview = self._previews.get(preview_id)
        if preview is None:
            raise SyncPreviewExpired("Bản xem trước đã hết hạn; hãy chọn lại file đồng bộ.")
        resolutions = conflict_resolutions or {}
        conflict_keys = {item["key"] for item in preview.conflicts}
        if set(resolutions) != conflict_keys or any(value not in {"local", "incoming"} for value in resolutions.values()):
            raise SyncError("Lựa chọn xử lý xung đột không hợp lệ.")

        payload = preview.payload
        manifest = payload["manifest"]
        package_id = manifest["package_id"]

        db_path = self._require_local_sqlite()
        stage_path: Path | None = None
        stage_engine: Engine | None = None
        data = payload["data"]
        with self.engine.connect() as live_conn:
            live_conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                if live_conn.execute(select(sync_history.c.package_id).where(sync_history.c.package_id == package_id)).first():
                    live_conn.rollback()
                    with self._lock:
                        self._previews.pop(preview_id, None)
                    return self._duplicate_result(package_id)

                current_conflicts, current_summary = self._compare(live_conn, data)
                current_state_hash = self._local_state_hash(live_conn)
                if (
                    current_state_hash != preview.local_state_hash
                    or self._comparison_snapshot(current_conflicts, current_summary) != self._comparison_snapshot(
                        preview.conflicts,
                        preview.summary,
                    )
                ):
                    with self._lock:
                        self._previews.pop(preview_id, None)
                    raise SyncPreviewExpired(
                        "Dữ liệu trên thiết bị đã thay đổi sau khi xem trước; hãy mở lại gói để kiểm tra xung đột mới."
                    )
                self._validate_cascade_resolutions(live_conn, data, current_conflicts, resolutions)

                # Giữ write lock từ trước lúc backup đến khi commit để không ghi đè một
                # import khác xảy ra trong thời gian staging. Toàn bộ merge/rebuild chạy
                # trên bản sao tạm, database người dùng chỉ bị thay đổi sau khi bản sao
                # đã qua quick_check, foreign_key_check và fingerprint KPI.
                backup_path = backup_sqlite_before_change(self.engine, "sync-import")
                if backup_path is None:
                    raise SyncError("Đồng bộ chỉ hỗ trợ SQLite local.")
                stage_path = self._allocate_stage_path(db_path)
                shutil.copy2(backup_path, stage_path)
                stage_engine = get_engine(f"sqlite:///{stage_path.as_posix()}")
                with stage_engine.begin() as stage_conn:
                    applied = self._apply_data(stage_conn, data, resolutions)
                    rebuilt = self._rebuild_versions(stage_conn)
                    summary = {"applied": applied, "rebuilt": rebuilt, "conflicts": resolutions}
                    stage_conn.execute(sync_history.insert().values(
                        package_id=package_id,
                        package_hash=preview.package_hash,
                        source_device_id=manifest["source_device"]["device_id"],
                        direction="import",
                        summary_json=summary,
                    ))
                    expected_fingerprint = self._validate_database(stage_conn)
                stage_engine.dispose()
                stage_engine = None

                self._replace_from_stage(live_conn, stage_path)
                actual_fingerprint = self._validate_database(live_conn)
                if actual_fingerprint != expected_fingerprint:
                    raise SyncError("KPI sau đồng bộ không khớp bản staging; dữ liệu chưa được thay đổi.")
                live_conn.commit()
                self._detach_stage(live_conn)
            except Exception:
                live_conn.rollback()
                self._detach_stage(live_conn)
                raise
            finally:
                if stage_engine is not None:
                    stage_engine.dispose()
                self._cleanup_stage(stage_path)
        with self._lock:
            self._previews.pop(preview_id, None)
        return {
            "duplicate": False,
            "already_imported": False,
            "changed": True,
            "package_id": package_id,
            "backup_path": backup_path,
            "applied": applied,
            "counts": applied,
            "rebuilt": rebuilt,
        }

    @staticmethod
    def _comparison_snapshot(
        conflicts: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> bytes:
        return _canonical({
            "conflicts": sorted(conflicts, key=lambda item: item["key"]),
            "summary": summary,
        })

    @staticmethod
    def _local_state_hash(conn) -> str:
        """Fingerprint every local row whose meaning can change a sync merge."""

        digest = hashlib.sha256()
        tables = (accounts, monthly_targets, import_batches, raw_import_rows, sync_tombstones)
        for table in tables:
            digest.update(table.name.encode("utf-8"))
            order_columns = tuple(table.primary_key.columns) or tuple(table.columns)
            rows = conn.execute(select(table).order_by(*order_columns)).mappings()
            for row in rows:
                normalized = {
                    key: SyncService._snapshot_value(value)
                    for key, value in row.items()
                }
                digest.update(_canonical(normalized))
        return digest.hexdigest()

    @staticmethod
    def _snapshot_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): SyncService._snapshot_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [SyncService._snapshot_value(item) for item in value]
        if isinstance(value, (datetime, date)):
            return _iso(value)
        if isinstance(value, bytes):
            return base64.b64encode(value).decode("ascii")
        return value

    @staticmethod
    def _duplicate_result(package_id: str) -> dict[str, Any]:
        return {
            "duplicate": True,
            "already_imported": True,
            "package_id": package_id,
            "changed": False,
            "counts": {"accounts": 0, "targets": 0, "import_batches": 0, "raw_rows": 0, "tombstones": 0},
        }

    @staticmethod
    def _allocate_stage_path(db_path: Path) -> Path:
        handle = tempfile.NamedTemporaryFile(
            prefix=f".{db_path.stem}-sync-stage-",
            suffix=db_path.suffix or ".db",
            dir=db_path.parent,
            delete=False,
        )
        path = Path(handle.name)
        handle.close()
        return path

    @staticmethod
    def _cleanup_stage(stage_path: Path | None) -> None:
        if stage_path is None:
            return
        for candidate in (
            stage_path,
            Path(f"{stage_path}-journal"),
            Path(f"{stage_path}-wal"),
            Path(f"{stage_path}-shm"),
        ):
            candidate.unlink(missing_ok=True)

    @staticmethod
    def _replace_from_stage(conn, stage_path: Path) -> None:
        conn.exec_driver_sql("ATTACH DATABASE ? AS sync_stage", (str(stage_path),)).close()
        delete_order = (
            raw_import_rows,
            order_line_versions,
            import_batches,
            monthly_targets,
            accounts,
            sync_tombstones,
            sync_history,
        )
        insert_order = (
            accounts,
            monthly_targets,
            import_batches,
            raw_import_rows,
            order_line_versions,
            sync_tombstones,
            sync_history,
        )
        for table in delete_order:
            conn.exec_driver_sql(f'DELETE FROM "{table.name}"').close()
        for table in insert_order:
            columns = ", ".join(f'"{column.name}"' for column in table.columns)
            conn.exec_driver_sql(
                f'INSERT INTO "{table.name}" ({columns}) '
                f'SELECT {columns} FROM sync_stage."{table.name}"'
            ).close()

    @staticmethod
    def _detach_stage(conn) -> None:
        try:
            conn.exec_driver_sql("DETACH DATABASE sync_stage").close()
        except Exception:
            pass

    @staticmethod
    def _validate_database(conn) -> dict[str, Any]:
        if conn.exec_driver_sql("PRAGMA quick_check").scalar_one() != "ok":
            raise SyncError("SQLite quick_check thất bại; dữ liệu chưa được thay đổi.")
        foreign_key_errors = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchmany(1)
        if foreign_key_errors:
            raise SyncError("SQLite foreign_key_check thất bại; dữ liệu chưa được thay đổi.")
        duplicate_current = conn.execute(
            select(order_line_versions.c.business_key)
            .where(order_line_versions.c.is_current.is_(True))
            .group_by(order_line_versions.c.business_key)
            .having(func.count() > 1)
            .limit(1)
        ).first()
        if duplicate_current:
            raise SyncError("Dữ liệu staging có nhiều phiên bản hiện hành cho cùng một đơn.")
        digest = hashlib.sha256()
        for row in conn.execute(
            select(
                order_line_versions.c.business_key,
                order_line_versions.c.normalized_hash,
                order_line_versions.c.status,
                order_line_versions.c.gmv,
                order_line_versions.c.estimated_commission,
                order_line_versions.c.final_received,
            )
            .where(order_line_versions.c.is_current.is_(True))
            .order_by(order_line_versions.c.business_key)
        ):
            digest.update(_canonical([_iso(value) for value in row]))
        return {
            "accounts": int(conn.execute(select(func.count()).select_from(accounts)).scalar_one()),
            "targets": int(conn.execute(select(func.count()).select_from(monthly_targets)).scalar_one()),
            "import_batches": int(conn.execute(select(func.count()).select_from(import_batches)).scalar_one()),
            "raw_rows": int(conn.execute(select(func.count()).select_from(raw_import_rows)).scalar_one()),
            "versions": int(conn.execute(select(func.count()).select_from(order_line_versions)).scalar_one()),
            "tombstones": int(conn.execute(select(func.count()).select_from(sync_tombstones)).scalar_one()),
            "history": int(conn.execute(select(func.count()).select_from(sync_history)).scalar_one()),
            "current_kpi_sha256": digest.hexdigest(),
        }

    def history(self, limit: int = 100) -> dict[str, Any]:
        self._require_local_sqlite()
        limit = max(1, min(int(limit), 200))
        with self.engine.connect() as conn:
            rows = conn.execute(select(sync_history).order_by(sync_history.c.created_at.desc()).limit(limit)).mappings().all()
        items = []
        for row in rows:
            summary = row["summary_json"] if isinstance(row["summary_json"], dict) else {}
            counts = summary.get("counts") or summary.get("applied") or {}
            items.append({
                "package_id": row["package_id"],
                "package_hash": row["package_hash"],
                "source_device_id": row["source_device_id"],
                "source_device": {"id": row["source_device_id"]},
                "direction": row["direction"],
                "status": "exported" if row["direction"] == "export" else "imported",
                "counts": counts,
                "created_at": _iso(row["created_at"]),
            })
        return {"items": items, "count": len(items)}

    @staticmethod
    def filename(now: datetime | None = None) -> str:
        stamp = (now or _utcnow()).strftime("%Y%m%d-%H%M%S")
        return f"AffiliateReport-{stamp}.affsync"

    def _require_local_sqlite(self) -> Path:
        return sqlite_file_path(self.engine)

    def _purge_previews(self) -> None:
        with self._lock:
            self._purge_previews_locked()

    def _purge_previews_locked(self) -> None:
        now = _utcnow()
        expired = [key for key, value in self._previews.items() if value.expires_at <= now]
        for key in expired:
            self._previews.pop(key, None)

    @staticmethod
    def _export_data(conn, device_id: str) -> dict[str, list[dict[str, Any]]]:
        exported_accounts = []
        for row in conn.execute(select(accounts).order_by(accounts.c.display_order, accounts.c.code)).mappings():
            sync_id = account_sync_id(row["code"])
            source_device_id = row["source_device_id"] or device_id
            sync_updated_at = row["sync_updated_at"] or row["updated_at"] or _utcnow()
            if not row["sync_id"] or not row["source_device_id"] or not row["sync_updated_at"]:
                conn.execute(update(accounts).where(accounts.c.code == row["code"]).values(
                    sync_id=sync_id,
                    source_device_id=source_device_id,
                    sync_updated_at=sync_updated_at,
                ))
            exported_accounts.append({
                "sync_id": sync_id,
                "code": row["code"],
                "display_name": row["display_name"],
                "active": bool(row["active"]),
                "display_order": int(row["display_order"]),
                "created_at": _iso(row["created_at"]),
                "updated_at": _iso(row["updated_at"]),
                "source_device_id": source_device_id,
                "sync_updated_at": _iso(sync_updated_at),
            })
        exported_targets = []
        for row in conn.execute(select(monthly_targets).order_by(monthly_targets.c.month, monthly_targets.c.account)).mappings():
            sync_id = target_sync_id(row["account"], row["month"])
            source_device_id = row["source_device_id"] or device_id
            sync_updated_at = row["sync_updated_at"] or _utcnow()
            if not row["sync_id"] or not row["source_device_id"] or not row["sync_updated_at"]:
                conn.execute(update(monthly_targets).where(monthly_targets.c.id == row["id"]).values(
                    sync_id=sync_id,
                    source_device_id=source_device_id,
                    sync_updated_at=sync_updated_at,
                ))
            exported_targets.append({
                "sync_id": sync_id,
                "account": row["account"],
                "month": _iso(row["month"]),
                "daily_target_commission": int(row["daily_target_commission"]),
                "source_device_id": source_device_id,
                "sync_updated_at": _iso(sync_updated_at),
            })
        exported_batches = []
        batch_ids: dict[int, str] = {}
        for row in conn.execute(select(import_batches).order_by(import_batches.c.created_at, import_batches.c.id)).mappings():
            sync_id = import_batch_sync_id(row["account"], row["file_sha"])
            source_device_id = row["source_device_id"] or device_id
            source_created_at = row["source_created_at"] or row["created_at"] or _utcnow()
            if not row["sync_id"] or not row["source_device_id"] or not row["source_created_at"]:
                conn.execute(update(import_batches).where(import_batches.c.id == row["id"]).values(
                    sync_id=sync_id,
                    source_device_id=source_device_id,
                    source_created_at=source_created_at,
                ))
            batch_ids[int(row["id"])] = sync_id
            exported_batches.append({
                "sync_id": sync_id,
                "file_sha": row["file_sha"],
                "filename": row["filename"],
                "account": row["account"],
                "inserted": int(row["inserted"]),
                "updated": int(row["updated"]),
                "unchanged": int(row["unchanged"]),
                "rejected": int(row["rejected"]),
                "source_device_id": source_device_id,
                "source_created_at": _iso(source_created_at),
            })
        exported_rows = []
        for row in conn.execute(select(raw_import_rows).order_by(raw_import_rows.c.batch_id, raw_import_rows.c.row_number)).mappings():
            sync_id = batch_ids.get(int(row["batch_id"]))
            if not sync_id:
                raise SyncError("Raw row tham chiếu import batch không tồn tại.")
            exported_rows.append({
                "batch_sync_id": sync_id,
                "row_number": int(row["row_number"]),
                "business_key": row["business_key"],
                "raw_json": row["raw_json"],
            })
        exported_tombstones = [
            {key: _iso(value) for key, value in row.items() if key != "id"}
            for row in conn.execute(select(sync_tombstones).order_by(sync_tombstones.c.deleted_at)).mappings()
        ]
        return {
            "accounts": exported_accounts,
            "targets": exported_targets,
            "import_batches": exported_batches,
            "raw_rows": exported_rows,
            "tombstones": exported_tombstones,
        }

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        if set(payload) != {"manifest", "data"} or not isinstance(payload["manifest"], dict) or not isinstance(payload["data"], dict):
            raise SyncError("Nội dung gói đồng bộ không đúng schema.")
        manifest = payload["manifest"]
        data = payload["data"]
        if manifest.get("schema") != PACKAGE_SCHEMA or manifest.get("app_id") != "affiliate-report":
            raise SyncError("Phiên bản gói đồng bộ không được hỗ trợ.")
        db_schema = manifest.get("db_schema")
        if not isinstance(db_schema, int) or isinstance(db_schema, bool) or not 1 <= db_schema <= DB_SCHEMA_VERSION:
            raise SyncError("Schema database của gói đồng bộ mới hơn phiên bản ứng dụng này.")
        manifest["package_id"] = _validate_uuid(manifest.get("package_id"), "package_id")
        _parse_datetime(manifest.get("exported_at"))
        source = manifest.get("source_device")
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("device_name"), str)
            or not 1 <= len(source["device_name"]) <= 128
            or not isinstance(source.get("platform"), str)
            or not 1 <= len(source["platform"]) <= 32
        ):
            raise SyncError("Gói đồng bộ thiếu danh tính thiết bị nguồn.")
        source["device_id"] = _validate_uuid(source.get("device_id"), "source_device.device_id")
        required = {"accounts", "targets", "import_batches", "raw_rows", "tombstones"}
        if set(data) != required or any(not isinstance(data[key], list) for key in required):
            raise SyncError("Các bảng trong gói đồng bộ không đúng schema.")
        if hashlib.sha256(_canonical(data)).hexdigest() != manifest.get("data_sha256"):
            raise SyncError("Checksum dữ liệu bên trong gói đồng bộ không khớp.")
        if manifest.get("counts") != {key: len(value) for key, value in data.items()}:
            raise SyncError("Số lượng bản ghi trong manifest không khớp.")

        batch_ids: set[str] = set()
        batch_aliases: dict[str, str] = {}
        batch_keys: set[tuple[str, str]] = set()
        for row in data["import_batches"]:
            if not isinstance(row, dict):
                raise SyncError("Import batch trong gói đồng bộ không hợp lệ.")
            sync_id = _validate_uuid(row.get("sync_id"), "import_batch.sync_id")
            key = (str(row.get("account", "")), str(row.get("file_sha", "")))
            if (
                sync_id in batch_ids
                or key in batch_keys
                or not _ACCOUNT_RE.fullmatch(key[0])
                or not _SHA256_RE.fullmatch(key[1])
                or not isinstance(row.get("filename"), str)
                or not 1 <= len(row["filename"]) <= 255
            ):
                raise SyncError("Gói đồng bộ chứa import batch trùng hoặc không hợp lệ.")
            _validate_uuid(row.get("source_device_id"), "import_batch.source_device_id")
            _parse_datetime(row.get("source_created_at"))
            stable_id = import_batch_sync_id(key[0], key[1])
            batch_aliases[sync_id] = stable_id
            row["sync_id"] = stable_id
            batch_ids.add(stable_id)
            batch_keys.add(key)
        seen_rows: set[tuple[str, int]] = set()
        for row in data["raw_rows"]:
            if not isinstance(row, dict) or row.get("batch_sync_id") not in batch_aliases:
                raise SyncError("Raw row tham chiếu import batch không hợp lệ.")
            row["batch_sync_id"] = batch_aliases[row["batch_sync_id"]]
            key = (row["batch_sync_id"], int(row.get("row_number", 0)))
            if key[1] < 2 or key in seen_rows or not isinstance(row.get("raw_json"), dict):
                raise SyncError("Raw row trong gói đồng bộ không hợp lệ.")
            seen_rows.add(key)
        account_sync_ids: set[str] = set()
        account_aliases: dict[str, str] = {}
        account_codes: set[str] = set()
        for row in data["accounts"]:
            if (
                not isinstance(row, dict)
                or not _ACCOUNT_RE.fullmatch(str(row.get("code", "")))
                or row.get("code") == "ALL"
                or not isinstance(row.get("display_name"), str)
                or not 1 <= len(row["display_name"].strip()) <= 128
                or not isinstance(row.get("display_order"), int)
            ):
                raise SyncError("Account trong gói đồng bộ không hợp lệ.")
            sync_id = _validate_uuid(row.get("sync_id"), "account.sync_id")
            if sync_id in account_sync_ids or row["code"] in account_codes:
                raise SyncError("Gói đồng bộ chứa account trùng sync_id hoặc code.")
            _validate_uuid(row.get("source_device_id"), "account.source_device_id")
            _parse_datetime(row.get("sync_updated_at"))
            stable_id = account_sync_id(row["code"])
            account_aliases[sync_id] = stable_id
            row["sync_id"] = stable_id
            account_sync_ids.add(stable_id)
            account_codes.add(row["code"])
        target_aliases: dict[str, str] = {}
        target_sync_ids: set[str] = set()
        for row in data["targets"]:
            if not isinstance(row, dict):
                raise SyncError("Target trong gói đồng bộ không hợp lệ.")
            old_sync_id = _validate_uuid(row.get("sync_id"), "target.sync_id")
            _validate_uuid(row.get("source_device_id"), "target.source_device_id")
            if not _ACCOUNT_RE.fullmatch(str(row.get("account", ""))) and row.get("account") != "ALL":
                raise SyncError("Target trong gói đồng bộ không hợp lệ.")
            amount = row.get("daily_target_commission")
            if not isinstance(amount, int) or isinstance(amount, bool) or not 0 <= amount <= 1_000_000_000_000:
                raise SyncError("Target trong gói đồng bộ không hợp lệ.")
            _parse_date(row.get("month"))
            _parse_datetime(row.get("sync_updated_at"))
            stable_id = target_sync_id(row["account"], row["month"])
            if stable_id in target_sync_ids:
                raise SyncError("Gói đồng bộ chứa target trùng account và tháng.")
            target_aliases[old_sync_id] = stable_id
            row["sync_id"] = stable_id
            target_sync_ids.add(stable_id)
        for row in data["tombstones"]:
            if not isinstance(row, dict) or row.get("entity_type") not in {"import_batch", "account", "target"}:
                raise SyncError("Tombstone trong gói đồng bộ không hợp lệ.")
            aliases = {
                "import_batch": batch_aliases,
                "account": account_aliases,
                "target": target_aliases,
            }[row["entity_type"]]
            row["entity_key"] = aliases.get(str(row.get("entity_key")), str(row.get("entity_key", "")))
            key = row["entity_key"]
            legacy_key = (
                row["entity_type"] == "account" and bool(_ACCOUNT_RE.fullmatch(key))
            ) or (
                row["entity_type"] == "target" and "|" in key
            )
            if not legacy_key:
                _validate_uuid(key, "tombstone.entity_key")
            _validate_uuid(row.get("source_device_id"), "tombstone.source_device_id")
            _parse_datetime(row.get("deleted_at"))
        live_keys = {
            *(('account', row['sync_id']) for row in data['accounts']),
            *(('target', row['sync_id']) for row in data['targets']),
            *(('import_batch', row['sync_id']) for row in data['import_batches']),
        }
        if any((row["entity_type"], row["entity_key"]) in live_keys for row in data["tombstones"]):
            raise SyncError("Gói đồng bộ chứa đồng thời dữ liệu đang dùng và dấu xóa cho cùng một mục.")

    @staticmethod
    def _validate_cascade_resolutions(
        conn,
        data: dict[str, list[dict[str, Any]]],
        conflicts: list[dict[str, Any]],
        resolutions: dict[str, str],
    ) -> None:
        conflict_by_key = {item["key"]: item for item in conflicts}

        def selected_is_deleted(item: dict[str, Any]) -> bool:
            selected = item.get(resolutions[item["key"]])
            return isinstance(selected, dict) and selected.get("deleted") is True

        local_account_codes = {
            row["sync_id"] or account_sync_id(row["code"]): row["code"]
            for row in conn.execute(select(accounts.c.sync_id, accounts.c.code)).mappings()
        }
        incoming_account_codes = {row["sync_id"]: row["code"] for row in data["accounts"]}
        target_accounts = {
            row["sync_id"] or target_sync_id(row["account"], row["month"]): row["account"]
            for row in conn.execute(select(monthly_targets.c.sync_id, monthly_targets.c.account, monthly_targets.c.month)).mappings()
        }
        target_accounts.update({row["sync_id"]: row["account"] for row in data["targets"]})
        batch_accounts = {
            row["sync_id"] or import_batch_sync_id(row["account"], row["file_sha"]): row["account"]
            for row in conn.execute(select(import_batches.c.sync_id, import_batches.c.account, import_batches.c.file_sha)).mappings()
        }
        batch_accounts.update({row["sync_id"]: row["account"] for row in data["import_batches"]})

        for key, account_conflict in conflict_by_key.items():
            prefix = "delete:account:"
            if not key.startswith(prefix) or not selected_is_deleted(account_conflict):
                continue
            account_sync = key[len(prefix):]
            account_code = incoming_account_codes.get(account_sync) or local_account_codes.get(account_sync)
            if not account_code:
                continue
            child_conflicts: list[dict[str, Any]] = []
            for child_key, child_conflict in conflict_by_key.items():
                if child_key.startswith("delete:target:"):
                    child_sync = child_key[len("delete:target:"):]
                    if target_accounts.get(child_sync) == account_code:
                        child_conflicts.append(child_conflict)
                elif child_key.startswith("delete:import_batch:"):
                    child_sync = child_key[len("delete:import_batch:"):]
                    if batch_accounts.get(child_sync) == account_code:
                        child_conflicts.append(child_conflict)
            if any(not selected_is_deleted(item) for item in child_conflicts):
                raise SyncError(
                    f"Không thể xóa account {account_code} nhưng giữ mục tiêu hoặc lịch sử nhập thuộc account đó. "
                    "Hãy chọn cùng phía xóa cho toàn bộ dữ liệu liên quan."
                )

    @staticmethod
    def _compare(conn, data: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        existing_accounts = {row["code"]: row for row in conn.execute(select(accounts)).mappings()}
        for incoming in data["accounts"]:
            local = existing_accounts.get(incoming["code"])
            if local and any(local[key] != incoming[key] for key in ("display_name", "active", "display_order")):
                conflicts.append({
                    "key": f"account:{incoming['code']}",
                    "id": f"account:{incoming['code']}",
                    "entity": "account",
                    "label": incoming["code"],
                    "local": {key: local[key] for key in ("display_name", "active", "display_order")},
                    "incoming": {key: incoming[key] for key in ("display_name", "active", "display_order")},
                    "default": "local",
                    "local_value": {key: local[key] for key in ("display_name", "active", "display_order")},
                    "incoming_value": {key: incoming[key] for key in ("display_name", "active", "display_order")},
                    "default_resolution": "local",
                })
        existing_targets = {
            (row["account"], _iso(row["month"])): row
            for row in conn.execute(select(monthly_targets)).mappings()
        }
        for incoming in data["targets"]:
            key = (incoming["account"], _iso(_parse_date(incoming["month"])))
            local = existing_targets.get(key)
            if local and int(local["daily_target_commission"]) != int(incoming["daily_target_commission"]):
                conflicts.append({
                    "key": f"target:{key[0]}|{key[1]}",
                    "id": f"target:{key[0]}|{key[1]}",
                    "entity": "target",
                    "label": f"{key[0]} {key[1][:7]}",
                    "local": {"daily_target_commission": int(local["daily_target_commission"])},
                    "incoming": {"daily_target_commission": int(incoming["daily_target_commission"])},
                    "default": "local",
                    "local_value": {"daily_target_commission": int(local["daily_target_commission"])},
                    "incoming_value": {"daily_target_commission": int(incoming["daily_target_commission"])},
                    "default_resolution": "local",
                })
        local_live: dict[tuple[str, str], dict[str, Any]] = {}
        for row in existing_accounts.values():
            local_live[("account", row["sync_id"] or account_sync_id(row["code"]))] = {
                "label": row["code"],
                "value": {
                    "display_name": row["display_name"],
                    "active": bool(row["active"]),
                    "updated_at": _iso(row["sync_updated_at"] or row["updated_at"]),
                },
            }
        for row in existing_targets.values():
            local_live[("target", row["sync_id"] or target_sync_id(row["account"], row["month"]))] = {
                "label": f"{row['account']} {_iso(row['month'])[:7]}",
                "value": {
                    "daily_target_commission": int(row["daily_target_commission"]),
                    "updated_at": _iso(row["sync_updated_at"]),
                },
            }
        local_batches = list(conn.execute(select(import_batches)).mappings())
        for row in local_batches:
            local_live[("import_batch", row["sync_id"] or import_batch_sync_id(row["account"], row["file_sha"]))] = {
                "label": f"{row['account']} · {row['filename']}",
                "value": {"filename": row["filename"], "created_at": _iso(row["source_created_at"] or row["created_at"])},
            }

        incoming_live: dict[tuple[str, str], dict[str, Any]] = {}
        for row in data["accounts"]:
            incoming_live[("account", row["sync_id"])] = {
                "label": row["code"],
                "value": {"display_name": row["display_name"], "active": bool(row["active"]), "updated_at": row["sync_updated_at"]},
            }
        for row in data["targets"]:
            incoming_live[("target", row["sync_id"])] = {
                "label": f"{row['account']} {row['month'][:7]}",
                "value": {"daily_target_commission": int(row["daily_target_commission"]), "updated_at": row["sync_updated_at"]},
            }
        for row in data["import_batches"]:
            incoming_live[("import_batch", row["sync_id"])] = {
                "label": f"{row['account']} · {row['filename']}",
                "value": {"filename": row["filename"], "created_at": row["source_created_at"]},
            }

        incoming_tombstones = {(row["entity_type"], row["entity_key"]): row for row in data["tombstones"]}
        local_tombstones = {
            (row["entity_type"], row["entity_key"]): row
            for row in conn.execute(select(sync_tombstones)).mappings()
        }
        for key, tombstone in incoming_tombstones.items():
            live = local_live.get(key)
            if live:
                conflict_key = f"delete:{key[0]}:{key[1]}"
                deletion = {"deleted": True, "deleted_at": _iso(_parse_datetime(tombstone["deleted_at"]))}
                conflicts.append({
                    "key": conflict_key,
                    "id": conflict_key,
                    "entity": key[0],
                    "label": f"Xóa {live['label']}" + (" và toàn bộ dữ liệu liên quan" if key[0] == "account" else ""),
                    "local": live["value"],
                    "incoming": deletion,
                    "default": "local",
                    "local_value": live["value"],
                    "incoming_value": deletion,
                    "default_resolution": "local",
                })
        for key, tombstone in local_tombstones.items():
            live = incoming_live.get(key)
            if live:
                conflict_key = f"delete:{key[0]}:{key[1]}"
                deletion = {"deleted": True, "deleted_at": _iso(tombstone["deleted_at"])}
                conflicts.append({
                    "key": conflict_key,
                    "id": conflict_key,
                    "entity": key[0],
                    "label": f"Khôi phục {live['label']}" + (" cùng dữ liệu liên quan" if key[0] == "account" else ""),
                    "local": deletion,
                    "incoming": live["value"],
                    "default": "local",
                    "local_value": deletion,
                    "incoming_value": live["value"],
                    "default_resolution": "local",
                })
        existing_sync_ids = set(conn.execute(select(import_batches.c.sync_id)).scalars())
        existing_batch_keys = set(conn.execute(select(import_batches.c.account, import_batches.c.file_sha)))
        new_batches = [
            row for row in data["import_batches"]
            if row["sync_id"] not in existing_sync_ids and (row["account"], row["file_sha"]) not in existing_batch_keys
        ]
        new_ids = {row["sync_id"] for row in new_batches}
        return conflicts, {
            "new_accounts": sum(1 for row in data["accounts"] if row["code"] not in existing_accounts),
            "new_targets": sum(1 for row in data["targets"] if (row["account"], _iso(_parse_date(row["month"]))) not in existing_targets),
            "new_import_batches": len(new_batches),
            "new_raw_rows": sum(1 for row in data["raw_rows"] if row["batch_sync_id"] in new_ids),
            "tombstones": len(data["tombstones"]),
        }

    @staticmethod
    def _apply_data(conn, data: dict[str, list[dict[str, Any]]], resolutions: dict[str, str]) -> dict[str, int]:
        counts = {"accounts": 0, "targets": 0, "import_batches": 0, "raw_rows": 0, "tombstones": 0}
        conn.execute(delete(order_line_versions))

        incoming_tombstones = {(row["entity_type"], row["entity_key"]): row for row in data["tombstones"]}
        local_live_keys = {
            *(('account', row[0] or account_sync_id(row[1])) for row in conn.execute(select(accounts.c.sync_id, accounts.c.code))),
            *(('target', row[0] or target_sync_id(row[1], row[2])) for row in conn.execute(select(monthly_targets.c.sync_id, monthly_targets.c.account, monthly_targets.c.month))),
            *(('import_batch', row[0] or import_batch_sync_id(row[1], row[2])) for row in conn.execute(select(import_batches.c.sync_id, import_batches.c.account, import_batches.c.file_sha))),
        }
        incoming_live_keys = {
            *(('account', row['sync_id']) for row in data['accounts']),
            *(('target', row['sync_id']) for row in data['targets']),
            *(('import_batch', row['sync_id']) for row in data['import_batches']),
        }
        local_tombstones = {
            (row["entity_type"], row["entity_key"]): row
            for row in conn.execute(select(sync_tombstones)).mappings()
        }
        for key in local_tombstones.keys() & incoming_live_keys:
            if resolutions[f"delete:{key[0]}:{key[1]}"] == "incoming":
                conn.execute(delete(sync_tombstones).where(
                    sync_tombstones.c.entity_type == key[0],
                    sync_tombstones.c.entity_key == key[1],
                ))
        for key, row in incoming_tombstones.items():
            if key in local_live_keys and resolutions[f"delete:{key[0]}:{key[1]}"] == "local":
                continue
            existing = conn.execute(select(sync_tombstones).where(
                sync_tombstones.c.entity_type == row["entity_type"],
                sync_tombstones.c.entity_key == row["entity_key"],
            )).mappings().first()
            deleted_at = _parse_datetime(row["deleted_at"])
            if existing and _parse_datetime(existing["deleted_at"]) and _parse_datetime(existing["deleted_at"]) >= deleted_at:
                continue
            if existing:
                conn.execute(update(sync_tombstones).where(sync_tombstones.c.id == existing["id"]).values(
                    deleted_at=deleted_at,
                    source_device_id=row["source_device_id"],
                ))
            else:
                conn.execute(sync_tombstones.insert().values(
                    entity_type=row["entity_type"], entity_key=row["entity_key"],
                    deleted_at=deleted_at, source_device_id=row["source_device_id"],
                ))
            counts["tombstones"] += 1

        effective_tombstones = {
            (row["entity_type"], row["entity_key"]): row
            for row in conn.execute(select(sync_tombstones)).mappings()
        }
        for (entity_type, entity_key), _row in effective_tombstones.items():
            if entity_type == "import_batch":
                batch = conn.execute(select(import_batches.c.id).where(import_batches.c.sync_id == entity_key)).first()
                if batch:
                    conn.execute(delete(raw_import_rows).where(raw_import_rows.c.batch_id == batch.id))
                    conn.execute(delete(import_batches).where(import_batches.c.id == batch.id))
            elif entity_type == "target":
                target = conn.execute(select(monthly_targets.c.id).where(monthly_targets.c.sync_id == entity_key)).first()
                if target:
                    conn.execute(delete(monthly_targets).where(monthly_targets.c.id == target.id))
                elif "|" in entity_key:  # tương thích package thử nghiệm trước v2.1.0
                    account, month = entity_key.split("|", 1)
                    conn.execute(delete(monthly_targets).where(
                        monthly_targets.c.account == account,
                        monthly_targets.c.month == _parse_date(month),
                    ))
            elif entity_type == "account":
                account_code = conn.execute(select(accounts.c.code).where(accounts.c.sync_id == entity_key)).scalar_one_or_none()
                if account_code is None and _ACCOUNT_RE.fullmatch(entity_key):
                    account_code = entity_key  # tương thích package thử nghiệm trước v2.1.0
                if account_code is None:
                    continue
                batch_ids = list(conn.execute(select(import_batches.c.id).where(import_batches.c.account == account_code)).scalars())
                if batch_ids:
                    conn.execute(delete(raw_import_rows).where(raw_import_rows.c.batch_id.in_(batch_ids)))
                conn.execute(delete(import_batches).where(import_batches.c.account == account_code))
                conn.execute(delete(monthly_targets).where(monthly_targets.c.account == account_code))
                conn.execute(delete(accounts).where(accounts.c.code == account_code))

        blocked_account_sync_ids = {key for entity, key in effective_tombstones if entity == "account"}
        blocked_account_codes = {
            row["code"] for row in data["accounts"] if row["sync_id"] in blocked_account_sync_ids
        }
        blocked_targets = {key for entity, key in effective_tombstones if entity == "target"}
        blocked_batches = {key for entity, key in effective_tombstones if entity == "import_batch"}

        for row in data["accounts"]:
            if row["sync_id"] in blocked_account_sync_ids:
                continue
            existing = conn.execute(select(accounts).where(accounts.c.code == row["code"])).mappings().first()
            values = {
                "sync_id": row["sync_id"],
                "display_name": str(row["display_name"])[:128],
                "active": bool(row["active"]),
                "display_order": int(row["display_order"]),
                "source_device_id": row.get("source_device_id"),
                "sync_updated_at": _parse_datetime(row.get("sync_updated_at")),
                "updated_at": _parse_datetime(row.get("updated_at")) or func.now(),
            }
            if existing:
                if resolutions.get(f"account:{row['code']}", "local") == "incoming":
                    conn.execute(update(accounts).where(accounts.c.code == row["code"]).values(**values))
                    counts["accounts"] += 1
            else:
                conn.execute(accounts.insert().values(code=row["code"], created_at=_parse_datetime(row.get("created_at")) or func.now(), **values))
                counts["accounts"] += 1

        for row in data["targets"]:
            month = _parse_date(row["month"])
            entity_key = f"{row['account']}|{_iso(month)}"
            if row["sync_id"] in blocked_targets or row["account"] in blocked_account_codes:
                continue
            existing = conn.execute(select(monthly_targets).where(
                monthly_targets.c.account == row["account"], monthly_targets.c.month == month,
            )).mappings().first()
            values = {
                "daily_target_commission": int(row["daily_target_commission"]),
                "sync_id": row["sync_id"],
                "source_device_id": row.get("source_device_id"),
                "sync_updated_at": _parse_datetime(row.get("sync_updated_at")),
            }
            if existing:
                if resolutions.get(f"target:{entity_key}", "local") == "incoming":
                    conn.execute(update(monthly_targets).where(monthly_targets.c.id == existing["id"]).values(**values))
                    counts["targets"] += 1
            else:
                conn.execute(monthly_targets.insert().values(account=row["account"], month=month, **values))
                counts["targets"] += 1

        rows_by_batch: dict[str, list[dict[str, Any]]] = {}
        for row in data["raw_rows"]:
            rows_by_batch.setdefault(row["batch_sync_id"], []).append(row)
        for row in sorted(data["import_batches"], key=lambda item: (item.get("source_created_at") or "", item["sync_id"])):
            if row["sync_id"] in blocked_batches or row["account"] in blocked_account_codes:
                continue
            same_id = conn.execute(select(import_batches).where(import_batches.c.sync_id == row["sync_id"])).mappings().first()
            if same_id:
                if same_id["file_sha"] != row["file_sha"] or same_id["account"] != row["account"]:
                    raise SyncError("Cùng sync_id nhưng import batch có nội dung khác nhau.")
                continue
            same_file = conn.execute(select(import_batches.c.id).where(
                import_batches.c.account == row["account"], import_batches.c.file_sha == row["file_sha"],
            )).first()
            if same_file:
                continue
            if not conn.execute(select(accounts.c.code).where(accounts.c.code == row["account"])).first():
                conn.execute(accounts.insert().values(
                    code=row["account"], sync_id=account_sync_id(row["account"]), display_name=row["account"], active=True, display_order=0,
                    source_device_id=row.get("source_device_id"), sync_updated_at=func.now(), updated_at=func.now(),
                ))
            batch_id = conn.execute(import_batches.insert().values(
                file_sha=row["file_sha"], filename=str(row["filename"])[:255], account=row["account"],
                inserted=0, updated=0, unchanged=0, rejected=int(row.get("rejected") or 0),
                sync_id=row["sync_id"], source_device_id=row.get("source_device_id"),
                source_created_at=_parse_datetime(row.get("source_created_at")),
                created_at=_parse_datetime(row.get("source_created_at")) or func.now(),
            )).inserted_primary_key[0]
            raw_values = [{
                "batch_id": batch_id,
                "row_number": int(raw["row_number"]),
                "business_key": raw["business_key"],
                "raw_json": raw["raw_json"],
            } for raw in rows_by_batch.get(row["sync_id"], [])]
            if raw_values:
                conn.execute(raw_import_rows.insert(), raw_values)
            counts["import_batches"] += 1
            counts["raw_rows"] += len(raw_values)
        return counts

    @staticmethod
    def _rebuild_versions(conn) -> dict[str, int]:
        current: dict[str, tuple[int, str, int]] = {}
        totals = {"versions": 0, "current": 0, "raw_rows": 0}
        batches = conn.execute(select(import_batches).order_by(
            import_batches.c.source_created_at, import_batches.c.sync_id, import_batches.c.id
        )).mappings().all()
        for batch in batches:
            batch_counts = {"inserted": 0, "updated": 0, "unchanged": 0}
            rows = conn.execute(select(raw_import_rows).where(raw_import_rows.c.batch_id == batch["id"]).order_by(raw_import_rows.c.row_number)).mappings()
            for raw in rows:
                totals["raw_rows"] += 1
                raw_json = dict(raw["raw_json"])
                # Các caller nội bộ/test cũ đôi khi truyền thẳng dòng đã normalize thay vì
                # `_raw`; SQLAlchemy đã JSON-hoá datetime thành ISO. Đổi lại thành datetime
                # để parser cho ra đúng normalized_hash như lần nhập ban đầu.
                for field in DATE_FIELDS:
                    value = raw_json.get(field)
                    if isinstance(value, str) and "-" in value:
                        try:
                            raw_json[field] = datetime.fromisoformat(value)
                        except ValueError:
                            pass
                normalized = normalize_row(raw_json, batch["account"])
                if normalized["business_key"] != raw["business_key"]:
                    raise SyncError("Raw row không khớp business_key; đã hủy đồng bộ.")
                existing = current.get(normalized["business_key"])
                if existing and existing[1] == normalized["normalized_hash"]:
                    batch_counts["unchanged"] += 1
                    continue
                version = existing[2] + 1 if existing else 1
                if existing:
                    conn.execute(update(order_line_versions).where(order_line_versions.c.id == existing[0]).values(is_current=False))
                    batch_counts["updated"] += 1
                else:
                    batch_counts["inserted"] += 1
                version_id = conn.execute(order_line_versions.insert().values(
                    business_key=normalized["business_key"], account=batch["account"],
                    order_id=normalized.get("ID đơn hàng"), sku_id=normalized.get("ID SKU"),
                    product_id=normalized.get("product_id"), product_name=normalized.get("Tên sản phẩm"),
                    shop_id=normalized.get("shop_id"), shop_name=normalized.get("shop_name"),
                    content_type=normalized.get("content_type"), content_id=normalized.get("content_id"),
                    order_type=normalized.get("order_type"), commission_type=normalized.get("commission_type"),
                    currency=normalized.get("currency"), status=normalized.get("status", "unknown"),
                    order_date=normalized.get("Ngày đặt hàng"), settlement_date=normalized.get("Ngày quyết toán hoa hồng"),
                    gmv=normalized.get("gmv") or 0, units_sold=normalized.get("units_sold") or 0,
                    units_refunded=normalized.get("units_refunded") or 0,
                    estimated_commission=normalized.get("estimated_commission") or 0,
                    final_received=normalized.get("final_received"), normalized_hash=normalized["normalized_hash"],
                    is_current=True, version=version, batch_id=batch["id"],
                )).inserted_primary_key[0]
                current[normalized["business_key"]] = (version_id, normalized["normalized_hash"], version)
                totals["versions"] += 1
            conn.execute(update(import_batches).where(import_batches.c.id == batch["id"]).values(**batch_counts))
        totals["current"] = len(current)
        return totals
