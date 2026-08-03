from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .version import APP_VERSION

DEFAULT_UPDATE_REPO = "anhtahaylove/tiktok-affiliate-report"
INSTALL_CONFIRMATION_PHRASE = "CAP NHAT UNG DUNG"
MAX_INSTALLER_BYTES = 250 * 1024 * 1024
MAX_CHECKSUM_BYTES = 1024 * 1024
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class UpdateError(RuntimeError):
    pass


def configured_repo() -> str:
    repo = os.getenv("TIKTOK_REPORT_UPDATE_REPO", DEFAULT_UPDATE_REPO).strip()
    if not REPO_RE.fullmatch(repo):
        raise UpdateError("Nguồn cập nhật GitHub không hợp lệ.")
    return repo


def github_token() -> str | None:
    for name in ("TIKTOK_REPORT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        if token := os.getenv(name, "").strip():
            return token
    if getattr(sys, "frozen", False) and os.getenv("TIKTOK_REPORT_USE_GH_CLI") != "1":
        return None
    gh = shutil.which("gh")
    if not gh:
        return None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        result = subprocess.run(
            [gh, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def check_for_update(*, current_version: str = APP_VERSION, token: str | None = None) -> dict[str, Any]:
    repo = configured_repo()
    release = _latest_release(repo, token if token is not None else github_token())
    latest_version = _parse_version(str(release.get("tag_name") or ""))
    current = _parse_version(current_version)
    installer_name = f"TikTokAffiliateReportSetup-v{'.'.join(map(str, latest_version))}.exe"
    asset_names = {str(asset.get("name")) for asset in release.get("assets") or []}
    return {
        "current_version": current_version,
        "latest_version": ".".join(map(str, latest_version)),
        "tag_name": str(release.get("tag_name") or ""),
        "available": latest_version > current,
        "installable": installer_name in asset_names and "SHA256SUMS.txt" in asset_names,
        "release_name": str(release.get("name") or release.get("tag_name") or ""),
        "release_url": str(release.get("html_url") or ""),
        "published_at": release.get("published_at"),
        "notes": str(release.get("body") or ""),
        "source_repo": repo,
    }


def download_latest_update(data_dir: Path, *, current_version: str = APP_VERSION, token: str | None = None) -> dict[str, Any]:
    repo = configured_repo()
    token = token if token is not None else github_token()
    release = _latest_release(repo, token)
    latest = _parse_version(str(release.get("tag_name") or ""))
    if latest <= _parse_version(current_version):
        raise UpdateError("Ứng dụng đang ở phiên bản mới nhất.")

    version = ".".join(map(str, latest))
    installer_name = f"TikTokAffiliateReportSetup-v{version}.exe"
    assets = {str(asset.get("name")): asset for asset in release.get("assets") or []}
    installer_asset = assets.get(installer_name)
    checksum_asset = assets.get("SHA256SUMS.txt")
    if not installer_asset or not checksum_asset:
        raise UpdateError("GitHub Release thiếu installer hoặc SHA256SUMS.txt.")

    target_dir = Path(data_dir).resolve() / "updates" / f"v{version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    checksum_path = target_dir / "SHA256SUMS.txt"
    installer_path = target_dir / installer_name
    _download_asset(checksum_asset, checksum_path, token, MAX_CHECKSUM_BYTES)
    expected_hash = _checksum_for(checksum_path.read_text(encoding="utf-8-sig"), installer_name)
    actual_hash = _download_asset(installer_asset, installer_path, token, MAX_INSTALLER_BYTES)
    if actual_hash != expected_hash:
        installer_path.unlink(missing_ok=True)
        raise UpdateError("SHA-256 của installer không khớp; đã hủy cập nhật.")
    return {
        "version": version,
        "installer_path": str(installer_path),
        "sha256": actual_hash,
        "release_url": str(release.get("html_url") or ""),
    }


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


def _latest_release(repo: str, token: str | None) -> dict[str, Any]:
    request = Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers=_headers(token, "application/vnd.github+json"),
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read(MAX_CHECKSUM_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403, 404}:
            raise UpdateError(
                "Không truy cập được nguồn cập nhật. Repository private cần GitHub token chỉ có quyền đọc Contents."
            ) from exc
        raise UpdateError(f"GitHub API trả về HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Không thể kết nối GitHub để kiểm tra cập nhật.") from exc
    if len(payload) > MAX_CHECKSUM_BYTES:
        raise UpdateError("Phản hồi GitHub Release quá lớn.")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub Release trả về dữ liệu không hợp lệ.") from exc
    if not isinstance(value, dict) or value.get("draft") or value.get("prerelease"):
        raise UpdateError("Không tìm thấy GitHub Release ổn định.")
    return value


def _download_asset(asset: dict[str, Any], destination: Path, token: str | None, max_bytes: int) -> str:
    url = str(asset.get("url") or "")
    size = int(asset.get("size") or 0)
    if not url.startswith("https://api.github.com/repos/") or size < 0 or size > max_bytes:
        raise UpdateError("GitHub Release asset không hợp lệ hoặc vượt giới hạn.")
    request = Request(url, headers=_headers(token, "application/octet-stream"))
    temporary = destination.with_suffix(destination.suffix + ".download")
    temporary.unlink(missing_ok=True)
    digest = hashlib.sha256()
    written = 0
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise UpdateError("GitHub Release asset vượt giới hạn tải xuống.")
                digest.update(chunk)
                handle.write(chunk)
    except UpdateError:
        temporary.unlink(missing_ok=True)
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise UpdateError("Không thể tải GitHub Release asset.") from exc
    if size and written != size:
        temporary.unlink(missing_ok=True)
        raise UpdateError("Kích thước GitHub Release asset không khớp.")
    actual_hash = digest.hexdigest().upper()
    asset_digest = str(asset.get("digest") or "")
    if not asset_digest.startswith("sha256:"):
        temporary.unlink(missing_ok=True)
        raise UpdateError("GitHub Release asset thiếu SHA-256 digest.")
    if asset_digest.lower() != f"sha256:{actual_hash.lower()}":
        temporary.unlink(missing_ok=True)
        raise UpdateError("Digest GitHub của Release asset không khớp.")
    os.replace(temporary, destination)
    return actual_hash


def _checksum_for(text: str, filename: str) -> str:
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9A-Fa-f]{64})\s+\*?(.+)", line.strip())
        if match and Path(match.group(2)).name == filename:
            return match.group(1).upper()
    raise UpdateError(f"SHA256SUMS.txt không có checksum cho {filename}.")


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
