from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .version import APP_VERSION

DEFAULT_UPDATE_FEED_URL = "https://raw.githubusercontent.com/anhtahaylove/tiktok-affiliate-report-updates/main/stable.json"
DEFAULT_UPDATE_REPO = "anhtahaylove/tiktok-affiliate-report-updates"
UPDATE_SCHEMA = "tiktok-affiliate-report.update.v1"
UPDATE_APP_ID = "tiktok-affiliate-report"
UPDATE_CHANNEL = "stable"
INSTALL_CONFIRMATION_PHRASE = "CAP NHAT UNG DUNG"
MAX_INSTALLER_BYTES = 250 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_CHECKSUM_BYTES = MAX_MANIFEST_BYTES
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
INSTALLER_RE = re.compile(r"^TikTokAffiliateReportSetup-v(\d+\.\d+\.\d+)\.exe$")
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


def check_for_update(*, current_version: str = APP_VERSION, token: str | None = None) -> dict[str, Any]:
    manifest = _latest_release(configured_feed_url())
    latest_version = _parse_version(str(manifest["version"]))
    current = _parse_version(current_version)
    installer = manifest["installer"]
    tag_name = f"v{manifest['version']}"
    return {
        "current_version": current_version,
        "latest_version": ".".join(map(str, latest_version)),
        "tag_name": tag_name,
        "available": latest_version > current,
        "installable": True,
        "release_name": tag_name,
        "release_url": str(manifest["release_url"]),
        "published_at": manifest.get("published_at"),
        "notes": "",
        "source_repo": configured_repo(),
        "feed_url": configured_feed_url(),
        "installer_name": str(installer["name"]),
    }


def download_latest_update(data_dir: Path, *, current_version: str = APP_VERSION, token: str | None = None) -> dict[str, Any]:
    manifest = _latest_release(configured_feed_url())
    latest = _parse_version(str(manifest["version"]))
    if latest <= _parse_version(current_version):
        raise UpdateError("Ứng dụng đang ở phiên bản mới nhất.")

    version = ".".join(map(str, latest))
    installer = manifest["installer"]
    installer_name = str(installer["name"])
    target_dir = Path(data_dir).resolve() / "updates" / f"v{version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    installer_path = target_dir / installer_name
    actual_hash = _download_file(str(installer["url"]), installer_path, int(installer["size"]), MAX_INSTALLER_BYTES)
    expected_hash = str(installer["sha256"]).upper()
    if actual_hash != expected_hash:
        installer_path.unlink(missing_ok=True)
        raise UpdateError("SHA-256 của installer không khớp; đã hủy cập nhật.")
    return {
        "version": version,
        "installer_path": str(installer_path),
        "sha256": actual_hash,
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
    return {
        "schema": UPDATE_SCHEMA,
        "app_id": UPDATE_APP_ID,
        "channel": UPDATE_CHANNEL,
        "version": version,
        "release_url": release_url,
        "published_at": value.get("published_at"),
        "installer": {"name": name, "url": url, "size": size, "sha256": sha256},
    }


def _download_file(url: str, destination: Path, expected_size: int, max_bytes: int) -> str:
    if expected_size <= 0 or expected_size > max_bytes:
        raise UpdateError("Kích thước update asset không hợp lệ.")
    temporary = destination.with_suffix(destination.suffix + ".download")
    temporary.unlink(missing_ok=True)
    digest = hashlib.sha256()
    written = 0
    try:
        with urlopen(Request(_require_https_url(url, "Update asset URL không hợp lệ."), headers=_headers(None, "application/octet-stream")), timeout=60) as response, temporary.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise UpdateError("Update asset vượt giới hạn tải xuống.")
                digest.update(chunk)
                handle.write(chunk)
    except UpdateError:
        temporary.unlink(missing_ok=True)
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise UpdateError("Không thể tải update asset.") from exc
    if written != expected_size:
        temporary.unlink(missing_ok=True)
        raise UpdateError("Kích thước update asset không khớp.")
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

def schedule_installer(
    installer_path: Path,
    expected_sha256: str,
    log_path: Path,
    shutdown: Callable[[], None],
    *,
    delay_seconds: float = 1.0,
) -> None:
    installer = Path(installer_path).resolve()
    expected = expected_sha256.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{64}", expected):
        raise UpdateError("SHA-256 của installer cập nhật không hợp lệ.")
    log = Path(log_path).resolve()
    _launch_update_helper(installer, expected, log)
    timer = threading.Timer(delay_seconds, shutdown)
    timer.daemon = True
    timer.start()


def _launch_update_helper(installer_path: Path, expected_sha256: str, log_path: Path) -> None:
    if not _windows_frozen():
        raise UpdateError("Cập nhật tự động chỉ chạy trong bản cài Windows.")
    if not installer_path.is_file() or not re.fullmatch(
        r"TikTokAffiliateReportSetup-v\d+\.\d+\.\d+\.exe",
        installer_path.name,
    ):
        raise UpdateError("Installer cập nhật không hợp lệ.")
    try:
        actual_sha256 = _file_sha256(installer_path)
    except OSError as exc:
        raise UpdateError("Không thể đọc installer cập nhật.") from exc
    if actual_sha256 != expected_sha256:
        raise UpdateError("Installer cập nhật đã thay đổi sau khi tải; đã hủy cập nhật.")

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

    helper_path = installer_path.parent / "install-update.ps1"
    installer_log = installer_path.parent / "installer.log"
    try:
        helper_path.write_text(
            """param(
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][string]$AppExe,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [Parameter(Mandatory=$true)][string]$InstallerLog
)
$ErrorActionPreference = 'Stop'
function Write-UpdateLog([string]$Message) {
    Add-Content -LiteralPath $LogPath -Value ((Get-Date -Format o) + ' ' + $Message) -Encoding UTF8
}
try {
    $parent = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
    if ($parent) { $parent | Wait-Process -Timeout 120 -ErrorAction Stop }
    $actual = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actual -ne $ExpectedSha256) { throw 'Installer SHA-256 changed after download.' }
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', ('/LOG="' + $InstallerLog + '"'))
    $process = Start-Process -FilePath $Installer -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $Installer) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer exited with code $($process.ExitCode)." }
    Write-UpdateLog 'Update installed successfully.'
} catch {
    Write-UpdateLog ('Update failed: ' + $_.Exception.Message)
} finally {
    try {
        if (-not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) {
            Start-Process -FilePath $AppExe -WorkingDirectory (Split-Path -Parent $AppExe)
        }
    } catch {
        Write-UpdateLog ('App restart failed: ' + $_.Exception.Message)
    }
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}
""",
            encoding="utf-8-sig",
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UpdateError("Không thể tạo updater helper.") from exc
    flags = (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    try:
        subprocess.Popen(
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
                str(helper_path),
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
            ],
            cwd=installer_path.parent,
            close_fds=True,
            creationflags=flags,
        )
    except OSError as exc:
        raise UpdateError("Không thể khởi chạy updater helper.") from exc


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
        "User-Agent": f"TikTokAffiliateReport/{APP_VERSION}",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
