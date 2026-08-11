from __future__ import annotations

import base64
import hashlib
import json
import os
import re
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

DEFAULT_UPDATE_FEED_URL = "https://raw.githubusercontent.com/anhtahaylove/tiktok-affiliate-report-updates/main/stable.json"
DEFAULT_UPDATE_REPO = "anhtahaylove/tiktok-affiliate-report-updates"
UPDATE_SCHEMA = "tiktok-affiliate-report.update.v1"
UPDATE_APP_ID = "tiktok-affiliate-report"
UPDATE_CHANNEL = "stable"
UPDATE_STATUS_SCHEMA = "tiktok-affiliate-report.update-status.v1"
UPDATE_STATUS_PHASES = {"idle", "downloading", "verifying", "waiting_for_exit", "installing", "restarting", "installed", "failed"}
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
    installer_name = str(installer["name"])
    target_dir = Path(data_dir).resolve() / "updates" / f"v{version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    installer_path = target_dir / installer_name
    actual_hash = _download_file(str(installer["url"]), installer_path, int(installer["size"]), MAX_INSTALLER_BYTES, progress_callback)
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
                if progress_callback:
                    progress_callback(written, expected_size)
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
        os.replace(tmp_name, target)
    except OSError as exc:
        Path(tmp_name).unlink(missing_ok=True)
        raise UpdateError("Không thể ghi trạng thái cập nhật.") from exc
    return status


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
        and status["phase"] in {"waiting_for_exit", "installing", "restarting"}
        and _parse_version(str(current_version)) == _parse_version(str(status["target_version"]))
    ):
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
    write_update_status(
        status,
        phase="verifying",
        target_version=target_version,
        bytes_downloaded=size,
        bytes_total=size,
    )
    _launch_update_helper(installer, expected, log, status, target_version, size, state)
    _wait_for_helper_handshake(status, target_version, installer.parent / "updater-bootstrap.log")
    timer = threading.Timer(delay_seconds, shutdown)
    timer.daemon = True
    timer.start()


def _launch_update_helper(
    installer_path: Path,
    expected_sha256: str,
    log_path: Path,
    status_path: Path,
    target_version: str,
    installer_size: int,
    instance_state_path: Path,
) -> None:
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
    bootstrap_log = installer_path.parent / "updater-bootstrap.log"
    try:
        helper_path.write_text(_powershell_helper_script(), encoding="utf-8-sig")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UpdateError("Không thể tạo updater helper.") from exc
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with bootstrap_log.open("ab") as bootstrap:
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
                    "-StatusPath",
                    str(status_path),
                    "-TargetVersion",
                    target_version,
                    "-InstallerSize",
                    str(installer_size),
                    "-InstanceStatePath",
                    str(instance_state_path),
                ],
                cwd=installer_path.parent,
                close_fds=True,
                creationflags=flags,
                stdout=bootstrap,
                stderr=bootstrap,
            )
    except OSError as exc:
        raise UpdateError("Không thể khởi chạy updater helper.") from exc


def _wait_for_helper_handshake(status_path: Path, target_version: str, bootstrap_log: Path, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            status = read_update_status(status_path)
        except UpdateError:
            status = None
        if status and status["target_version"] == target_version:
            if status["phase"] in {"waiting_for_exit", "installing", "restarting", "installed"}:
                return
            if status["phase"] == "failed":
                raise UpdateError(str(status["error"] or "Updater helper khởi động thất bại."))
        time.sleep(0.1)
    detail = ""
    try:
        if bootstrap_log.is_file() and bootstrap_log.stat().st_size <= 64 * 1024:
            detail = bootstrap_log.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        detail = ""
    raise UpdateError("Updater helper không xác nhận khởi động." + (f" {detail}" if detail else ""))


def _powershell_helper_script() -> str:
    return r'''
param(
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][string]$AppExe,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [Parameter(Mandatory=$true)][string]$InstallerLog,
    [Parameter(Mandatory=$true)][string]$StatusPath,
    [Parameter(Mandatory=$true)][string]$TargetVersion,
    [Parameter(Mandatory=$true)][int64]$InstallerSize,
    [Parameter(Mandatory=$true)][string]$InstanceStatePath
)
$ErrorActionPreference = 'Stop'
$Utf8 = [System.Text.UTF8Encoding]::new($false)
function Escape-Json([string]$Value) {
    if ($null -eq $Value) { return '' }
    return $Value.Replace('\', '\\').Replace('"', '\"').Replace("`r", '\r').Replace("`n", '\n')
}
function Ensure-Directory([string]$FilePath) {
    $directory = [System.IO.Path]::GetDirectoryName($FilePath)
    if ($directory) { [System.IO.Directory]::CreateDirectory($directory) > $null }
}
function Write-UpdateLog([string]$Message) {
    Ensure-Directory $LogPath
    [System.IO.File]::AppendAllText($LogPath, ([System.DateTimeOffset]::UtcNow.ToString('o') + ' ' + $Message + [System.Environment]::NewLine), $Utf8)
}
function Write-UpdateStatus([string]$Phase, [string]$ErrorText) {
    Ensure-Directory $StatusPath
    $errorJson = 'null'
    if ($ErrorText) { $errorJson = '"' + (Escape-Json $ErrorText) + '"' }
    $json = '{"bytes_downloaded":' + $InstallerSize + ',"bytes_total":' + $InstallerSize + ',"error":' + $errorJson + ',"phase":"' + $Phase + '","schema":"tiktok-affiliate-report.update-status.v1","target_version":"' + (Escape-Json $TargetVersion) + '","updated_at":"' + [System.DateTimeOffset]::UtcNow.ToString('o') + '"}'
    $tmp = $StatusPath + '.' + $PID + '.tmp'
    [System.IO.File]::WriteAllText($tmp, $json + [System.Environment]::NewLine, $Utf8)
    if ([System.IO.File]::Exists($StatusPath)) {
        $backup = $StatusPath + '.' + $PID + '.bak'
        try {
            if ([System.IO.File]::Exists($backup)) { [System.IO.File]::Delete($backup) }
            [System.IO.File]::Replace($tmp, $StatusPath, $backup, $true)
        } finally {
            try { if ([System.IO.File]::Exists($backup)) { [System.IO.File]::Delete($backup) } } catch {}
        }
    } else {
        [System.IO.File]::Move($tmp, $StatusPath)
    }
}
function Get-Sha256Hex([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToUpperInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}
function Start-Child([string]$FilePath, [string]$Arguments, [string]$WorkingDirectory, [bool]$Wait) {
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $process = [System.Diagnostics.Process]::Start($psi)
    if ($Wait) { $process.WaitForExit(); return $process.ExitCode }
    return 0
}
function Wait-FileUnlocked([string]$Path, [int]$TimeoutMs) {
    # $ParentPid is only the PyInstaller onefile *child* process. Its bootloader parent keeps
    # $AppExe open a little longer while it unpacks/cleans up its _MEI temp directory, so
    # WaitForExit($ParentPid) alone can return before the file is actually unlocked. If the
    # installer's /CLOSEAPPLICATIONS still finds it in use it defaults to Abort (exit code 5)
    # instead of prompting, since Setup runs /SUPPRESSMSGBOXES. Poll the file handle itself
    # (deliberately not enumerating processes — see forbidden cmdlets in test_updater.py) so we
    # cover any lingering process, not just the one PID we happen to know about.
    $deadline = [System.Diagnostics.Stopwatch]::StartNew()
    while ($deadline.ElapsedMilliseconds -lt $TimeoutMs) {
        if (-not [System.IO.File]::Exists($Path)) { return $true }
        try {
            $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            $stream.Close()
            return $true
        } catch [System.IO.IOException] {
            Start-Sleep -Milliseconds 200
        }
    }
    return $false
}
function Test-Health([string]$Url) {
    try {
        $client = [System.Net.WebClient]::new()
        try {
            $client.DownloadString($Url + '/health') | Out-Null
            return $true
        } finally { $client.Dispose() }
    } catch {
        return $false
    }
}
function Wait-AppHealthy([string]$StatePath, [int]$TimeoutMs) {
    # The relaunched app writes instance.json (with its /health URL) once its window-station-
    # bound startup (single-instance mutex, then the system tray icon) clears — that step has
    # been observed to stall for several seconds right after a fresh install, likely antivirus
    # scanning the newly-written exe. Poll for a real response instead of assuming Start-Child
    # succeeding means the app is actually usable yet.
    $deadline = [System.Diagnostics.Stopwatch]::StartNew()
    while ($deadline.ElapsedMilliseconds -lt $TimeoutMs) {
        if ([System.IO.File]::Exists($StatePath)) {
            try {
                $raw = [System.IO.File]::ReadAllText($StatePath)
                $match = [System.Text.RegularExpressions.Regex]::Match($raw, '"url"\s*:\s*"([^"]+)"')
                if ($match.Success -and (Test-Health $match.Groups[1].Value)) { return $true }
            } catch {}
        }
        Start-Sleep -Milliseconds 400
    }
    return $false
}
$parentExited = $false
try {
    Write-UpdateLog 'Updater helper started.'
    Write-UpdateStatus 'waiting_for_exit' $null
    try {
        $parent = [System.Diagnostics.Process]::GetProcessById($ParentPid)
        if (-not $parent.WaitForExit(120000)) { throw 'Timed out waiting for app to exit.' }
    } catch [System.ArgumentException] {
    }
    $parentExited = $true
    if (-not (Wait-FileUnlocked $AppExe 15000)) {
        Write-UpdateLog 'Warning: app executable still locked 15s after process exit; proceeding anyway.'
    }
    Write-UpdateStatus 'installing' $null
    if (([System.IO.FileInfo]::new($Installer)).Length -ne $InstallerSize) { throw 'Installer size changed after download.' }
    $actual = Get-Sha256Hex $Installer
    if ($actual -ne $ExpectedSha256) { throw 'Installer SHA-256 changed after download.' }
    $arguments = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LOG="' + $InstallerLog + '"'
    $exitCode = Start-Child $Installer $arguments ([System.IO.Path]::GetDirectoryName($Installer)) $true
    if ($exitCode -ne 0) { throw "Installer exited with code $exitCode." }
    Write-UpdateStatus 'restarting' $null
    Start-Child $AppExe '--updated' ([System.IO.Path]::GetDirectoryName($AppExe)) $false > $null
    # Bản onedir không giải nén runtime ra %TEMP% nữa. Mở ngay sau khi cài thường mất 2-4s vì
    # installer vừa ghi xong nên file còn trong cache của OS; nhưng mở nguội (file đã rơi khỏi
    # cache, antivirus quét lại gần 1.800 file) đã đo được tới 35s trên máy thật. Cho 90s để một
    # lần khởi động chậm không bị báo nhầm là hỏng — chờ lâu giờ chẳng hại gì nữa.
    #
    # KHÔNG mở lần thứ hai khi chờ quá hạn. Bản onefile trước đây làm vậy và chính đó là thứ sinh
    # ra hộp thoại "Failed to load Python DLL": hai tiến trình cùng giải nén tranh nhau đĩa và
    # antivirus, một trong hai nạp DLL hỏng giữa chừng. Chờ không thấy thì báo thật cho người dùng.
    if (-not (Wait-AppHealthy $InstanceStatePath 90000)) {
        Write-UpdateLog 'Warning: install succeeded but the app did not report healthy within 45s; leaving it to the user to open.'
        Write-UpdateStatus 'installed' 'Đã cài xong nhưng ứng dụng chưa tự mở lại được. Hãy mở TikTok Affiliate Report từ Desktop hoặc Start Menu.'
        Write-UpdateLog 'Update installed successfully.'
        return
    }
    Write-UpdateLog 'Update installed successfully.'
} catch {
    $failure = $_.Exception.Message
    try { Write-UpdateStatus 'failed' $failure } catch {}
    try { Write-UpdateLog ('Update failed: ' + $failure) } catch {}
    if ($parentExited -and [System.IO.File]::Exists($AppExe)) {
        try {
            Start-Child $AppExe '' ([System.IO.Path]::GetDirectoryName($AppExe)) $false > $null
            Write-UpdateLog 'Previous app version restarted after update failure.'
        } catch {
            Write-UpdateLog ('App restart failed: ' + $_.Exception.Message)
        }
    }
} finally {
    try { [System.IO.File]::Delete($PSCommandPath) } catch {}
}
'''


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
