from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .version import APP_VERSION

# Feed chuyển về chính repo nguồn (nay đã public) để bỏ bớt một repo phải trông.
# Bản 2.0.10 trở về trước ghim URL cũ, nên repo cũ phải sống tới khi mọi máy đã lên >= 2.0.11.
DEFAULT_UPDATE_FEED_URL = "https://raw.githubusercontent.com/anhtahaylove/affiliate-report/main/stable.json"
DEFAULT_UPDATE_REPO = "anhtahaylove/affiliate-report"
# Địa chỉ cũ, giữ lại làm dự phòng sau khi repo đã đổi tên thành affiliate-report. Máy nào còn
# ở bản trước v2.0.25 vẫn đọc địa chỉ này, và bản v2.0.25 biết cả hai — nên dù chuyển hướng của
# GitHub cho raw.githubusercontent.com có hoạt động hay không thì vẫn tìm được feed. Xoá được
# khi chắc chắn không còn máy nào chạy bản cũ hơn v2.0.26.
FALLBACK_UPDATE_FEED_URLS = (
    "https://raw.githubusercontent.com/anhtahaylove/tiktok-affiliate-report/main/stable.json",
)
UPDATE_SCHEMA = "tiktok-affiliate-report.update.v1"
UPDATE_APP_ID = "tiktok-affiliate-report"
UPDATE_CHANNEL = "stable"
UPDATE_STATUS_SCHEMA = "tiktok-affiliate-report.update-status.v1"
UPDATE_STATUS_PHASES = {"idle", "downloading", "verifying", "waiting_for_exit", "installing", "restarting", "installed", "failed"}
INSTALL_CONFIRMATION_PHRASE = "CAP NHAT UNG DUNG"
# Tải lại vài lần trước khi báo hỏng: gói ~46 MB, một cú rớt mạng không đáng làm hỏng cả bản
# cập nhật. Ba lần là đủ vượt qua sự cố thoáng qua mà không bắt người dùng chờ vô hạn.
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_RETRY_DELAYS = (2.0, 5.0)
MAX_INSTALLER_BYTES = 250 * 1024 * 1024
MAX_BOOTSTRAP_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_CHECKSUM_BYTES = MAX_MANIFEST_BYTES
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
# Chấp nhận CẢ tên cũ lẫn tên sau khi đổi thương hiệu.
#
# Đây là bản lề của cả đợt đổi tên. Bản đang chạy trên máy người dùng tự kiểm tên tệp tải về
# trước khi cho chạy; nếu nó chỉ biết tên cũ thì bản phát hành đầu tiên mang tên mới sẽ bị
# chính nó từ chối, và máy kẹt vĩnh viễn ở phiên bản cũ — không sửa được bằng auto-update vì
# đường cập nhật đã đứt. Vì vậy phải phát hành bản nới lỏng này TRƯỚC, đợi mọi máy lên tới
# đây, rồi mới đổi tên. Sau khi không còn máy nào chạy bản cũ hơn thì thu hẹp lại được.
INSTALLER_RE = re.compile(r"^(?:TikTok)?AffiliateReportSetup-v(\d+\.\d+\.\d+)\.exe$")
UPDATE_BOOTSTRAP_PROTOCOL = 1
UPDATE_BOOTSTRAP_VERSION = "1.0.0"
UPDATE_BOOTSTRAP_NAME = f"TikTokAffiliateUpdater-v{UPDATE_BOOTSTRAP_VERSION}.ps1"
BOOTSTRAP_RE = re.compile(r"^(?:TikTok)?AffiliateUpdater-v(\d+\.\d+\.\d+)\.ps1$")
BOOTSTRAP_ACK_SCHEMA = "tiktok-affiliate-report.update-bootstrap-ack.v1"
SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
TRUSTED_UPDATE_KEYS = {
    "tiktok-report-updates-2026-08": "hA5aOGFJdfDjtm9ME52d/2lBMlAPLao+bg5wlPM4Tm0=",
}


class UpdateError(RuntimeError):
    pass


def configured_feed_url() -> str:
    override = os.getenv("TIKTOK_REPORT_UPDATE_FEED_URL", "").strip()
    if override:
        if getattr(sys, "frozen", False):
            raise UpdateError("Không cho phép đổi nguồn cập nhật trong bản cài Windows.")
        return _require_https_url(override, "Nguồn cập nhật dev không hợp lệ.")
    return DEFAULT_UPDATE_FEED_URL


def configured_repo() -> str:
    """Compatibility shim for older callers; updates now use the signed public feed."""
    parsed = urlparse(DEFAULT_UPDATE_FEED_URL)
    parts = parsed.path.strip("/").split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else DEFAULT_UPDATE_REPO


def github_token() -> None:
    """Compatibility shim: public update checks must never need or send a token."""
    return None


def _latest_release_with_fallback() -> dict[str, Any]:
    """Đọc feed ở nguồn chính, hỏng thì thử nguồn dự phòng.

    Đổi tên repo GitHub làm URL feed đổi theo. Tài liệu GitHub nói rõ git clone/fetch/push được
    chuyển hướng, nhưng KHÔNG nói gì về raw.githubusercontent.com — mà đó chính là đường app đọc
    feed. Đặt cược vào một chuyển hướng không được ghi nhận, để đổi lấy nguy cơ mọi máy mất khả
    năng tự cập nhật, là canh bạc không đáng.

    Chữ ký Ed25519 vẫn được kiểm y hệt ở cả hai nguồn, nên nguồn dự phòng không nới lỏng bảo mật
    — nó chỉ là địa chỉ thứ hai để tìm cùng một tệp đã ký. Xoá được sau khi đổi tên xong xuôi.
    """
    urls = [configured_feed_url()]
    if not os.getenv("TIKTOK_REPORT_UPDATE_FEED_URL", "").strip():
        urls.extend(url for url in FALLBACK_UPDATE_FEED_URLS if url not in urls)
    loi: Exception | None = None
    for url in urls:
        try:
            return _latest_release(url)
        except (UpdateError, OSError) as exc:
            loi = exc
    raise loi if loi is not None else UpdateError("Không đọc được nguồn cập nhật.")


def check_for_update(*, current_version: str = APP_VERSION, token: str | None = None) -> dict[str, Any]:
    manifest = _latest_release_with_fallback()
    latest_version = _parse_version(str(manifest["version"]))
    current = _parse_version(current_version)
    installer = manifest["installer"]
    bootstrap = manifest.get("bootstrap")
    tag_name = f"v{manifest['version']}"
    result = {
        "current_version": current_version,
        "latest_version": ".".join(map(str, latest_version)),
        "tag_name": tag_name,
        "available": latest_version > current,
        "installable": bootstrap is not None,
        "release_name": tag_name,
        "release_url": str(manifest["release_url"]),
        "published_at": manifest.get("published_at"),
        "notes": "",
        "source_repo": configured_repo(),
        "feed_url": configured_feed_url(),
        "installer_name": str(installer["name"]),
    }
    if bootstrap is not None:
        result["bootstrap_protocol"] = int(bootstrap["protocol"])
        result["bootstrap_version"] = str(bootstrap["version"])
    return result


def download_latest_update(
    data_dir: Path,
    *,
    current_version: str = APP_VERSION,
    token: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    manifest = _latest_release(configured_feed_url())
    latest = _parse_version(str(manifest["version"]))
    if latest <= _parse_version(current_version):
        raise UpdateError("Ứng dụng đang ở phiên bản mới nhất.")

    version = ".".join(map(str, latest))
    installer = manifest["installer"]
    bootstrap = manifest.get("bootstrap")
    if not isinstance(bootstrap, dict):
        raise UpdateError("Update manifest thiếu updater bootstrap; không thể cài tự động.")
    installer_name = str(installer["name"])
    target_dir = Path(data_dir).resolve() / "updates" / f"v{version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    installer_path = target_dir / installer_name
    bootstrap_path = target_dir / str(bootstrap["name"])
    installer_size = int(installer["size"])
    bootstrap_size = int(bootstrap["size"])
    total_size = installer_size + bootstrap_size

    def report_installer(done: int, _total: int) -> None:
        if progress_callback:
            progress_callback(done, total_size)

    def report_bootstrap(done: int, _total: int) -> None:
        if progress_callback:
            progress_callback(installer_size + done, total_size)

    actual_hash = _download_file(str(installer["url"]), installer_path, installer_size, MAX_INSTALLER_BYTES, report_installer)
    expected_hash = str(installer["sha256"]).upper()
    if actual_hash != expected_hash:
        installer_path.unlink(missing_ok=True)
        raise UpdateError("SHA-256 của installer không khớp; đã hủy cập nhật.")
    try:
        actual_bootstrap_hash = _download_file(
            str(bootstrap["url"]),
            bootstrap_path,
            bootstrap_size,
            MAX_BOOTSTRAP_BYTES,
            report_bootstrap,
        )
    except Exception:
        bootstrap_path.unlink(missing_ok=True)
        installer_path.unlink(missing_ok=True)
        raise
    expected_bootstrap_hash = str(bootstrap["sha256"]).upper()
    if actual_bootstrap_hash != expected_bootstrap_hash:
        bootstrap_path.unlink(missing_ok=True)
        installer_path.unlink(missing_ok=True)
        raise UpdateError("SHA-256 của updater bootstrap không khớp; đã hủy cập nhật.")
    return {
        "version": version,
        "installer_path": str(installer_path),
        "sha256": actual_hash,
        "bootstrap_path": str(bootstrap_path),
        "bootstrap_sha256": actual_bootstrap_hash,
        "bootstrap_protocol": int(bootstrap["protocol"]),
        "bootstrap_version": str(bootstrap["version"]),
        "release_url": str(manifest["release_url"]),
    }


def _latest_release(feed_url: str, token: str | None = None) -> dict[str, Any]:
    if token:
        raise UpdateError("Nguồn cập nhật công khai không dùng GitHub token.")
    manifest_bytes = _read_url(_require_https_url(feed_url, "Nguồn cập nhật không hợp lệ."), MAX_MANIFEST_BYTES)
    sig_url = urljoin(feed_url, Path(urlparse(feed_url).path).name + ".sig")
    return verify_update_manifest_bytes(manifest_bytes, _read_url(_require_https_url(sig_url, "Chữ ký update không hợp lệ."), 16 * 1024))


def verify_update_manifest_bytes(manifest_bytes: bytes, signature_bytes: bytes) -> dict[str, Any]:
    signature = _parse_signature(signature_bytes)
    _verify_manifest_signature(manifest_bytes, signature)
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Update manifest không hợp lệ.") from exc
    return _validate_manifest(manifest)


def _parse_signature(signature_bytes: bytes) -> dict[str, str]:
    try:
        value = json.loads(signature_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Chữ ký update không hợp lệ.") from exc
    if not isinstance(value, dict):
        raise UpdateError("Chữ ký update không hợp lệ.")
    return {"key_id": str(value.get("key_id") or ""), "signature": str(value.get("signature") or "")}


def _verify_manifest_signature(manifest_bytes: bytes, signature: dict[str, str]) -> None:
    public_key_b64 = TRUSTED_UPDATE_KEYS.get(signature["key_id"])
    if not public_key_b64:
        raise UpdateError("Update manifest dùng key_id không được tin cậy.")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        public_key.verify(base64.b64decode(signature["signature"], validate=True), manifest_bytes)
    except (InvalidSignature, ValueError) as exc:
        raise UpdateError("Chữ ký update manifest không hợp lệ.") from exc


def _validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != UPDATE_SCHEMA:
        raise UpdateError("Update manifest không đúng schema.")
    if value.get("app_id") != UPDATE_APP_ID:
        raise UpdateError("Update manifest không đúng app_id.")
    if value.get("channel") != UPDATE_CHANNEL:
        raise UpdateError("Update manifest không đúng channel.")
    version = str(value.get("version") or "")
    parsed_version = _parse_version(version)
    release_url = _require_https_url(str(value.get("release_url") or ""), "Release URL không hợp lệ.")
    installer = value.get("installer")
    if not isinstance(installer, dict):
        raise UpdateError("Update manifest thiếu installer.")
    name = str(installer.get("name") or "")
    match = INSTALLER_RE.fullmatch(name)
    if not match or match.group(1) != version:
        raise UpdateError("Tên installer trong update manifest không hợp lệ.")
    size = installer.get("size")
    if not isinstance(size, int) or size <= 0 or size > MAX_INSTALLER_BYTES:
        raise UpdateError("Kích thước installer trong update manifest không hợp lệ.")
    sha256 = str(installer.get("sha256") or "").upper()
    if not SHA256_RE.fullmatch(sha256):
        raise UpdateError("SHA-256 installer trong update manifest không hợp lệ.")
    url = _require_https_url(str(installer.get("url") or ""), "Installer URL trong update manifest không hợp lệ.")
    if Path(urlparse(url).path).name != name:
        raise UpdateError("Installer URL không khớp tên file trong update manifest.")
    bootstrap = value.get("bootstrap")
    if bootstrap is None:
        bootstrap_value = None
    elif not isinstance(bootstrap, dict):
        raise UpdateError("Updater bootstrap trong update manifest không hợp lệ.")
    else:
        bootstrap_value = bootstrap
    if bootstrap_value is not None:
        bootstrap = bootstrap_value
        protocol = bootstrap.get("protocol")
        if protocol != UPDATE_BOOTSTRAP_PROTOCOL:
            raise UpdateError("Updater bootstrap dùng protocol không được hỗ trợ.")
        bootstrap_version = str(bootstrap.get("version") or "")
        bootstrap_name = str(bootstrap.get("name") or "")
        bootstrap_match = BOOTSTRAP_RE.fullmatch(bootstrap_name)
        try:
            _parse_version(bootstrap_version)
        except UpdateError as exc:
            raise UpdateError("Tên hoặc phiên bản updater bootstrap không hợp lệ.") from exc
        if not bootstrap_match or bootstrap_match.group(1) != bootstrap_version:
            raise UpdateError("Tên hoặc phiên bản updater bootstrap không hợp lệ.")
        bootstrap_size = bootstrap.get("size")
        if not isinstance(bootstrap_size, int) or bootstrap_size <= 0 or bootstrap_size > MAX_BOOTSTRAP_BYTES:
            raise UpdateError("Kích thước updater bootstrap không hợp lệ.")
        bootstrap_sha256 = str(bootstrap.get("sha256") or "").upper()
        if not SHA256_RE.fullmatch(bootstrap_sha256):
            raise UpdateError("SHA-256 updater bootstrap không hợp lệ.")
        bootstrap_url = _require_https_url(
            str(bootstrap.get("url") or ""),
            "Updater bootstrap URL không hợp lệ.",
        )
        if Path(urlparse(bootstrap_url).path).name != bootstrap_name:
            raise UpdateError("Updater bootstrap URL không khớp tên file.")
    result = {
        "schema": UPDATE_SCHEMA,
        "app_id": UPDATE_APP_ID,
        "channel": UPDATE_CHANNEL,
        "version": version,
        "release_url": release_url,
        "published_at": value.get("published_at"),
        "installer": {"name": name, "url": url, "size": size, "sha256": sha256},
    }
    if bootstrap_value is not None:
        result["bootstrap"] = {
            "protocol": protocol,
            "version": bootstrap_version,
            "name": bootstrap_name,
            "url": bootstrap_url,
            "size": bootstrap_size,
            "sha256": bootstrap_sha256,
        }
    return result


def _download_file(
    url: str,
    destination: Path,
    expected_size: int,
    max_bytes: int,
    progress_callback: Callable[[int, int], None] | None = None,
) -> str:
    if expected_size <= 0 or expected_size > max_bytes:
        raise UpdateError("Kích thước update asset không hợp lệ.")
    temporary = destination.with_suffix(destination.suffix + ".download")
    safe_url = _require_https_url(url, "Update asset URL không hợp lệ.")
    digest = hashlib.sha256()
    written = 0
    # Gói cài nặng ~46 MB. Một cú rớt mạng hay một lần GitHub trả 503 là cả bản cập nhật hỏng và
    # người dùng phải tự bấm "Thử lại" — đo được trên gate cập nhật thật: máy báo đúng lỗi này
    # trong khi các máy khác cùng lúc tải xong bình thường. Thử lại vài lần trước khi bỏ cuộc.
    # Chỉ thử lại lỗi mạng; sai kích thước hay vượt giới hạn là lỗi toàn vẹn, phải nổi ngay.
    last_network_error: Exception | None = None
    for attempt in range(_DOWNLOAD_ATTEMPTS):
        temporary.unlink(missing_ok=True)
        digest = hashlib.sha256()
        written = 0
        try:
            with urlopen(Request(safe_url, headers=_headers(None, "application/octet-stream")), timeout=60) as response, temporary.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise UpdateError("Update asset vượt giới hạn tải xuống.")
                    digest.update(chunk)
                    handle.write(chunk)
                    if progress_callback:
                        progress_callback(written, expected_size)
        except UpdateError:
            temporary.unlink(missing_ok=True)
            raise
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_network_error = exc
            if attempt == _DOWNLOAD_ATTEMPTS - 1:
                temporary.unlink(missing_ok=True)
                raise UpdateError("Không thể tải update asset.") from exc
            time.sleep(_DOWNLOAD_RETRY_DELAYS[attempt])
            continue
        # Tải xong mà thiếu byte cũng là đứt giữa chừng, không phải gói hỏng — thử lại được.
        if written != expected_size:
            if attempt == _DOWNLOAD_ATTEMPTS - 1:
                temporary.unlink(missing_ok=True)
                raise UpdateError("Kích thước update asset không khớp.")
            time.sleep(_DOWNLOAD_RETRY_DELAYS[attempt])
            continue
        break
    else:  # pragma: no cover - vòng lặp luôn thoát bằng break hoặc raise
        temporary.unlink(missing_ok=True)
        raise UpdateError("Không thể tải update asset.") from last_network_error
    os.replace(temporary, destination)
    return digest.hexdigest().upper()


def _read_url(url: str, max_bytes: int) -> bytes:
    try:
        with urlopen(Request(url, headers=_headers(None, "application/json")), timeout=20) as response:
            payload = response.read(max_bytes + 1)
    except HTTPError as exc:
        raise UpdateError(f"Nguồn cập nhật trả về HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Không thể kết nối nguồn cập nhật.") from exc
    if len(payload) > max_bytes:
        raise UpdateError("Nguồn cập nhật trả về dữ liệu quá lớn.")
    return payload


def _require_https_url(value: str, message: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise UpdateError(message)
    return value


def _download_asset(asset: dict[str, Any], destination: Path, token: str | None, max_bytes: int) -> str:
    """Compatibility shim for older tests/callers; release assets are now direct public URLs."""
    return _download_file(str(asset.get("url") or ""), destination, int(asset.get("size") or 0), max_bytes)


def _checksum_for(text: str, filename: str) -> str:
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9A-Fa-f]{64})\s+\*?(.+)", line.strip())
        if match and Path(match.group(2)).name == filename:
            return match.group(1).upper()
    raise UpdateError(f"SHA256SUMS.txt không có checksum cho {filename}.")


def write_update_status(
    path: Path,
    *,
    phase: str,
    target_version: str | None = None,
    bytes_downloaded: int = 0,
    bytes_total: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    status = _validate_update_status(
        {
            "schema": UPDATE_STATUS_SCHEMA,
            "phase": phase,
            "target_version": target_version,
            "bytes_downloaded": bytes_downloaded,
            "bytes_total": bytes_total,
            "error": error,
            "updated_at": _utc_now(),
        }
    )
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(status, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        _replace_with_retry(tmp_name, target)
    except OSError as exc:
        Path(tmp_name).unlink(missing_ok=True)
        raise UpdateError("Không thể ghi trạng thái cập nhật.") from exc
    return status


def _replace_with_retry(source: str, target: Path, timeout: float = 2.0) -> None:
    """Thay file trạng thái, chịu được việc có ai đó đang mở đọc đúng lúc đó.

    Trên Windows os.replace dùng MoveFileEx và ném PermissionError nếu file đích đang được mở —
    kể cả chỉ mở để đọc. Endpoint /progress đọc đúng file này và giao diện hỏi nó mỗi 750 ms
    trong suốt lúc cài, nên hai bên va nhau là chuyện sẽ xảy ra chứ không phải có thể xảy ra:
    đo trên gate cập nhật thật, 2 trong 5 lần cài hỏng ngay ở lần ghi trạng thái đầu tiên với
    đúng lỗi này, và cả bản cập nhật bị bỏ dở.

    Bên đọc chỉ giữ file trong khoảnh khắc nên thử lại là đủ. Hết thời gian thì vẫn ném lỗi
    như cũ, không nuốt.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


def read_update_status(path: Path, current_version: str = APP_VERSION) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _idle_update_status()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Trạng thái cập nhật không hợp lệ.") from exc
    status = _validate_update_status(value)
    if (
        status["target_version"]
        and status["phase"] in {"waiting_for_exit", "installing", "restarting", "installed"}
        and _parse_version(str(current_version)) >= _parse_version(str(status["target_version"]))
    ):
        # Reaching this API from the target (or a newer) version proves that the
        # relaunched app is healthy. Keep any raw helper timeout on disk for
        # diagnostics, but do not expose it as an active problem to the UI.
        return {**status, "phase": "installed", "error": None}
    return status


def _idle_update_status() -> dict[str, Any]:
    return {
        "schema": UPDATE_STATUS_SCHEMA,
        "phase": "idle",
        "target_version": None,
        "bytes_downloaded": 0,
        "bytes_total": 0,
        "error": None,
        "updated_at": _utc_now(),
    }


def _validate_update_status(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != UPDATE_STATUS_SCHEMA:
        raise UpdateError("Trạng thái cập nhật không đúng schema.")
    phase = str(value.get("phase") or "")
    if phase not in UPDATE_STATUS_PHASES:
        raise UpdateError("Trạng thái cập nhật không đúng phase.")
    target_version = value.get("target_version")
    if target_version is not None:
        target_version = str(target_version)
        _parse_version(target_version)
    try:
        bytes_downloaded = int(value.get("bytes_downloaded", 0))
        bytes_total = int(value.get("bytes_total", 0))
    except (TypeError, ValueError) as exc:
        raise UpdateError("Trạng thái cập nhật không đúng bytes.") from exc
    if bytes_downloaded < 0 or bytes_total < 0 or bytes_downloaded > bytes_total > 0:
        raise UpdateError("Trạng thái cập nhật không đúng bytes.")
    error = value.get("error")
    updated_at = str(value.get("updated_at") or "")
    if not updated_at:
        raise UpdateError("Trạng thái cập nhật thiếu thời điểm cập nhật.")
    return {
        "schema": UPDATE_STATUS_SCHEMA,
        "phase": phase,
        "target_version": target_version,
        "bytes_downloaded": bytes_downloaded,
        "bytes_total": bytes_total,
        "error": None if error is None else str(error),
        "updated_at": updated_at,
    }


def public_update_issue(phase: str, error: str | None) -> tuple[str | None, str | None]:
    """Return stable user copy without exposing helper internals or local paths."""
    if not error:
        return None, None
    normalized = error.casefold()
    if phase == "installed":
        return (
            "Đã cài bản cập nhật nhưng ứng dụng chưa tự mở lại.",
            "Mở Affiliate Report từ Desktop hoặc Start Menu, sau đó kiểm tra lại phiên bản.",
        )
    if any(token in normalized for token in ("sha-256", "checksum", "signature", "chữ ký", "tamper", "changed", "kích thước")):
        return (
            "Gói cập nhật không vượt qua bước xác minh an toàn.",
            "Bấm “Thử lại” để tải lại gói. Nếu lỗi tiếp diễn, hãy mở trang phát hành hoặc liên hệ người hỗ trợ.",
        )
    if any(token in normalized for token in ("download", "không thể tải", "kết nối", "network", "http ", "timed out", "timeout")):
        return (
            "Không thể tải gói cập nhật từ nguồn phát hành.",
            "Kiểm tra kết nối mạng rồi bấm “Thử lại”.",
        )
    return (
        "Không thể hoàn tất cài đặt bản cập nhật.",
        "Bấm “Thử lại” để tải lại gói. Nếu lỗi tiếp diễn, hãy mở trang phát hành hoặc liên hệ người hỗ trợ.",
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def schedule_installer(
    installer_path: Path,
    expected_sha256: str,
    log_path: Path,
    shutdown: Callable[[], None],
    *,
    status_path: Path,
    target_version: str,
    bootstrap_path: Path,
    bootstrap_sha256: str,
    bootstrap_protocol: int,
    bootstrap_version: str,
    installer_size: int | None = None,
    delay_seconds: float = 1.0,
    instance_state_path: Path | None = None,
) -> None:
    installer = Path(installer_path).resolve()
    expected = expected_sha256.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{64}", expected):
        raise UpdateError("SHA-256 của installer cập nhật không hợp lệ.")
    if _parse_version(target_version) <= (0, 0, 0):
        raise UpdateError("Phiên bản cập nhật không hợp lệ.")
    log = Path(log_path).resolve()
    status = Path(status_path).resolve()
    # installer sits at <data_dir>/updates/v<version>/<name>.exe; instance.json (written by
    # desktop_launcher on every launch) lives at <data_dir>/instance.json unless the caller
    # points at a different location explicitly.
    state = Path(instance_state_path).resolve() if instance_state_path else installer.parent.parent.parent / "instance.json"
    size = installer_size or installer.stat().st_size
    bootstrap = Path(bootstrap_path).resolve()
    attempt_id = secrets.token_hex(16)
    ack_path = installer.parent / "bootstrap-ack.json"
    ack_path.unlink(missing_ok=True)
    write_update_status(
        status,
        phase="verifying",
        target_version=target_version,
        bytes_downloaded=size,
        bytes_total=size,
    )
    helper_process = _launch_update_bootstrap(
        installer_path=installer,
        expected_sha256=expected,
        bootstrap_path=bootstrap,
        expected_bootstrap_sha256=bootstrap_sha256,
        bootstrap_protocol=bootstrap_protocol,
        bootstrap_version=bootstrap_version,
        log_path=log,
        status_path=status,
        target_version=target_version,
        installer_size=size,
        instance_state_path=state,
        attempt_id=attempt_id,
        ack_path=ack_path,
    )
    try:
        _wait_for_bootstrap_handshake(
            ack_path,
            attempt_id=attempt_id,
            target_version=target_version,
            bootstrap_protocol=bootstrap_protocol,
            bootstrap_version=bootstrap_version,
            bootstrap_log=installer.parent / "updater-bootstrap.log",
        )
    except Exception as exc:
        cleanup_issue = _stop_update_helper(helper_process)
        if cleanup_issue:
            note = f"Không thể xác nhận updater helper đã dừng: {cleanup_issue}"
            exc.add_note(note)
            try:
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a", encoding="utf-8") as stream:
                    stream.write(f"{_utc_now()} {note}\n")
            except OSError:
                pass
        raise
    timer = threading.Timer(delay_seconds, shutdown)
    timer.daemon = True
    timer.start()


def _launch_update_bootstrap(
    *,
    installer_path: Path,
    expected_sha256: str,
    bootstrap_path: Path,
    expected_bootstrap_sha256: str,
    bootstrap_protocol: int,
    bootstrap_version: str,
    log_path: Path,
    status_path: Path,
    target_version: str,
    installer_size: int,
    instance_state_path: Path,
    attempt_id: str,
    ack_path: Path,
) -> subprocess.Popen[Any]:
    if not _windows_frozen():
        raise UpdateError("Cập nhật tự động chỉ chạy trong bản cài Windows.")
    if not installer_path.is_file() or not re.fullmatch(
        r"AffiliateReportSetup-v\d+\.\d+\.\d+\.exe",
        installer_path.name,
    ):
        raise UpdateError("Installer cập nhật không hợp lệ.")
    try:
        actual_sha256 = _file_sha256(installer_path)
    except OSError as exc:
        raise UpdateError("Không thể đọc installer cập nhật.") from exc
    if actual_sha256 != expected_sha256:
        raise UpdateError("Installer cập nhật đã thay đổi sau khi tải; đã hủy cập nhật.")
    bootstrap_match = BOOTSTRAP_RE.fullmatch(bootstrap_path.name)
    if (
        bootstrap_protocol != UPDATE_BOOTSTRAP_PROTOCOL
        or not bootstrap_match
        or bootstrap_match.group(1) != bootstrap_version
        or not bootstrap_path.is_file()
    ):
        raise UpdateError("Updater bootstrap không hợp lệ.")
    expected_bootstrap = expected_bootstrap_sha256.strip().upper()
    if not SHA256_RE.fullmatch(expected_bootstrap):
        raise UpdateError("SHA-256 updater bootstrap không hợp lệ.")
    try:
        actual_bootstrap_sha256 = _file_sha256(bootstrap_path)
    except OSError as exc:
        raise UpdateError("Không thể đọc updater bootstrap.") from exc
    if actual_bootstrap_sha256 != expected_bootstrap:
        raise UpdateError("Updater bootstrap đã thay đổi sau khi tải; đã hủy cập nhật.")
    if not re.fullmatch(r"[A-Fa-f0-9]{32}", attempt_id):
        raise UpdateError("Mã lần cập nhật không hợp lệ.")

    app_path = Path(sys.executable).resolve()
    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    if not app_path.is_file() or not powershell.is_file():
        raise UpdateError("Không tìm thấy Windows app hoặc updater helper.")

    installer_log = installer_path.parent / "installer.log"
    bootstrap_log = installer_path.parent / "updater-bootstrap.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.parent.mkdir(parents=True, exist_ok=True)
        ack_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UpdateError("Không thể chuẩn bị updater bootstrap.") from exc
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with bootstrap_log.open("ab") as bootstrap:
            return subprocess.Popen(
                [
                    str(powershell),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    str(bootstrap_path),
                    "-ParentPid",
                    str(os.getpid()),
                    "-Installer",
                    str(installer_path),
                    "-ExpectedSha256",
                    expected_sha256,
                    "-AppExe",
                    str(app_path),
                    "-LogPath",
                    str(log_path),
                    "-InstallerLog",
                    str(installer_log),
                    "-StatusPath",
                    str(status_path),
                    "-TargetVersion",
                    target_version,
                    "-InstallerSize",
                    str(installer_size),
                    "-InstanceStatePath",
                    str(instance_state_path),
                    "-BootstrapProtocol",
                    str(bootstrap_protocol),
                    "-BootstrapVersion",
                    bootstrap_version,
                    "-AttemptId",
                    attempt_id,
                    "-AckPath",
                    str(ack_path),
                ],
                cwd=installer_path.parent,
                close_fds=True,
                creationflags=flags,
                stdout=bootstrap,
                stderr=bootstrap,
            )
    except OSError as exc:
        raise UpdateError("Không thể khởi chạy updater bootstrap.") from exc


def _stop_update_helper(process: subprocess.Popen[Any] | None) -> str | None:
    if process is None:
        return None
    try:
        if process.poll() is not None:
            return None
    except OSError:
        # The handle may still support terminate/kill even if poll failed.
        pass
    try:
        process.terminate()
    except OSError:
        # Escalate to kill below; a failed terminate alone is recoverable.
        pass
    else:
        try:
            process.wait(timeout=5)
            return None
        except subprocess.TimeoutExpired:
            pass
        except OSError:
            pass
    try:
        process.kill()
    except OSError as exc:
        return f"không thể dừng tiến trình helper ({exc})."
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return "tiến trình helper không thoát sau khi terminate/kill."
    except OSError as exc:
        return f"không thể xác nhận tiến trình helper đã thoát ({exc})."
    return None


def _wait_for_bootstrap_handshake(
    ack_path: Path,
    *,
    attempt_id: str,
    target_version: str,
    bootstrap_protocol: int,
    bootstrap_version: str,
    bootstrap_log: Path,
    timeout_seconds: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            value = json.loads(ack_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and value.get("attempt_id") == attempt_id:
            if (
                value.get("schema") == BOOTSTRAP_ACK_SCHEMA
                and value.get("phase") == "ready"
                and value.get("protocol") == bootstrap_protocol
                and value.get("bootstrap_version") == bootstrap_version
                and value.get("target_version") == target_version
            ):
                return
            raise UpdateError("Updater bootstrap trả về handshake không hợp lệ.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.1, remaining))
    detail = ""
    try:
        if bootstrap_log.is_file() and bootstrap_log.stat().st_size <= 64 * 1024:
            detail = bootstrap_log.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        detail = ""
    raise UpdateError("Updater bootstrap không xác nhận khởi động." + (f" {detail}" if detail else ""))


def _windows_frozen() -> bool:
    return os.name == "nt" and bool(getattr(sys, "frozen", False))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        raise UpdateError(f"Phiên bản không hợp lệ: {value!r}.")
    return tuple(map(int, match.groups()))


def _headers(token: str | None, accept: str) -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": f"AffiliateReport/{APP_VERSION}",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
