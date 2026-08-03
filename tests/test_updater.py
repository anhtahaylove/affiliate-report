from __future__ import annotations

import hashlib
import io
import json
import threading
from pathlib import Path

import pytest

import tiktok_affiliate_report.updater as updater


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def release(installer: bytes, checksum: bytes) -> dict:
    return {
        "tag_name": "v1.2.0",
        "name": "v1.2.0",
        "html_url": "https://github.com/anhtahaylove/tiktok-affiliate-report/releases/tag/v1.2.0",
        "published_at": "2026-08-04T00:00:00Z",
        "body": "Update",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": "TikTokAffiliateReportSetup-v1.2.0.exe",
                "url": "https://api.github.com/repos/x/y/releases/assets/1",
                "size": len(installer),
                "digest": f"sha256:{hashlib.sha256(installer).hexdigest()}",
            },
            {
                "name": "SHA256SUMS.txt",
                "url": "https://api.github.com/repos/x/y/releases/assets/2",
                "size": len(checksum),
                "digest": f"sha256:{hashlib.sha256(checksum).hexdigest()}",
            },
        ],
    }


def test_check_and_download_update_with_verified_checksum(tmp_path, monkeypatch):
    installer = b"installer"
    digest = hashlib.sha256(installer).hexdigest().upper()
    checksum = f"{digest}  TikTokAffiliateReportSetup-v1.2.0.exe\n".encode()
    payload = json.dumps(release(installer, checksum)).encode()

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/releases/latest"):
            return Response(payload)
        return Response(installer if request.full_url.endswith("/1") else checksum)

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    monkeypatch.setattr(updater, "github_token", lambda: None)

    checked = updater.check_for_update(current_version="1.1.1")
    downloaded = updater.download_latest_update(tmp_path, current_version="1.1.1")

    assert checked["available"] is True
    assert checked["installable"] is True
    assert downloaded["sha256"] == digest
    assert Path(downloaded["installer_path"]).read_bytes() == installer


def test_download_rejects_checksum_mismatch(tmp_path, monkeypatch):
    installer = b"tampered"
    checksum = ("0" * 64 + "  TikTokAffiliateReportSetup-v1.2.0.exe\n").encode()
    payload = json.dumps(release(installer, checksum)).encode()

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/releases/latest"):
            return Response(payload)
        return Response(installer if request.full_url.endswith("/1") else checksum)

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    monkeypatch.setattr(updater, "github_token", lambda: None)

    with pytest.raises(updater.UpdateError, match="SHA-256"):
        updater.download_latest_update(tmp_path, current_version="1.1.1")
    assert not list(tmp_path.rglob("*.exe"))


def test_download_rejects_github_asset_digest_mismatch(tmp_path, monkeypatch):
    installer = b"installer"
    digest = hashlib.sha256(installer).hexdigest().upper()
    checksum = f"{digest}  TikTokAffiliateReportSetup-v1.2.0.exe\n".encode()
    release_payload = release(installer, checksum)
    release_payload["assets"][0]["digest"] = "sha256:" + "0" * 64
    payload = json.dumps(release_payload).encode()

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/releases/latest"):
            return Response(payload)
        return Response(installer if request.full_url.endswith("/1") else checksum)

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    monkeypatch.setattr(updater, "github_token", lambda: None)

    with pytest.raises(updater.UpdateError, match="Digest GitHub"):
        updater.download_latest_update(tmp_path, current_version="1.1.1")
    assert not list(tmp_path.rglob("*.exe"))


def test_windows_update_helper_waits_verifies_installs_and_restarts(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.0.exe"
    installer.write_bytes(b"installer")
    expected = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    app = tmp_path / "TikTokAffiliateReport.exe"
    app.write_bytes(b"app")
    system_root = tmp_path / "Windows"
    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    powershell.parent.mkdir(parents=True)
    powershell.write_bytes(b"powershell")
    captured = {}

    monkeypatch.setattr(updater, "_windows_frozen", lambda: True)
    monkeypatch.setenv("SystemRoot", str(system_root))
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(app))
    monkeypatch.setattr(updater.subprocess, "DETACHED_PROCESS", 8, raising=False)
    monkeypatch.setattr(updater.subprocess, "CREATE_NEW_PROCESS_GROUP", 16, raising=False)
    monkeypatch.setattr(updater.subprocess, "CREATE_NO_WINDOW", 32, raising=False)

    def fake_popen(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)

    updater._launch_update_helper(installer, expected, tmp_path / "updater.log")

    helper_path = installer.parent / "install-update.ps1"
    helper = helper_path.read_text(encoding="utf-8-sig")
    assert "Wait-Process -Timeout 120" in helper
    assert "Get-FileHash -LiteralPath $Installer -Algorithm SHA256" in helper
    assert "'/VERYSILENT'" in helper
    assert "Start-Process -FilePath $AppExe" in helper
    assert captured["args"][0] == str(powershell)
    assert captured["args"][captured["args"].index("-File") + 1] == str(helper_path)
    assert captured["args"][captured["args"].index("-ExpectedSha256") + 1] == expected
    assert captured["kwargs"]["cwd"] == installer.parent
    assert captured["kwargs"]["creationflags"] == 56


def test_scheduled_installer_rechecks_sha256_before_launch(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.0.exe"
    installer.write_bytes(b"tampered")
    log_path = tmp_path / "updater.log"
    shutdown = threading.Event()
    monkeypatch.setattr(updater, "_windows_frozen", lambda: True)

    with pytest.raises(updater.UpdateError, match="đã thay đổi"):
        updater.schedule_installer(installer, "0" * 64, log_path, shutdown.set, delay_seconds=0)

    assert not shutdown.is_set()


def test_version_and_repo_validation(monkeypatch):
    monkeypatch.setenv("TIKTOK_REPORT_UPDATE_REPO", "https://evil.example/repo")
    with pytest.raises(updater.UpdateError, match="không hợp lệ"):
        updater.check_for_update()
    with pytest.raises(updater.UpdateError, match="Phiên bản"):
        updater._parse_version("1.2")


def test_frozen_app_does_not_run_gh_cli_without_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    for name in ("TIKTOK_REPORT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "TIKTOK_REPORT_USE_GH_CLI"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(updater.shutil, "which", lambda _name: pytest.fail("gh lookup must not run"))

    assert updater.github_token() is None
