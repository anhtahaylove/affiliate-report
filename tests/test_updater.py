from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tiktok_affiliate_report.updater as updater
from scripts import sign_update_feed

TEST_KEY_ID = "test-key"
TEST_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
TEST_PUBLIC_B64 = base64.b64encode(
    TEST_PRIVATE.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).decode("ascii")
NEXT_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65)))
NEXT_PUBLIC_B64 = base64.b64encode(
    NEXT_PRIVATE.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).decode("ascii")


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def stable_feed(
    installer: bytes = b"installer",
    version: str = "1.2.1",
    *,
    signing_key: Ed25519PrivateKey = TEST_PRIVATE,
    key_id: str = TEST_KEY_ID,
    **overrides,
):
    name = overrides.pop("name", f"TikTokAffiliateReportSetup-v{version}.exe")
    installer_info = overrides.pop("installer_info", None)
    manifest = {
        "schema": updater.UPDATE_SCHEMA,
        "app_id": updater.UPDATE_APP_ID,
        "channel": updater.UPDATE_CHANNEL,
        "version": version,
        "published_at": "2026-08-04T00:00:00Z",
        "release_url": f"https://github.com/anhtahaylove/tiktok-affiliate-report-updates/releases/tag/v{version}",
        "installer": installer_info or {
            "name": name,
            "url": f"https://github.com/anhtahaylove/tiktok-affiliate-report-updates/releases/download/v{version}/{name}",
            "size": len(installer),
            "sha256": hashlib.sha256(installer).hexdigest().upper(),
        },
    }
    manifest.update(overrides)
    payload = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    signature = json.dumps(
        {"key_id": key_id, "signature": base64.b64encode(signing_key.sign(payload)).decode("ascii")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return payload, signature, installer


def install_feed(monkeypatch, manifest: bytes, signature: bytes, installer: bytes = b"installer", trusted_keys=None):
    seen_headers = []

    def fake_urlopen(request, timeout):
        seen_headers.append(dict(request.header_items()))
        if request.full_url.endswith("stable.json"):
            return Response(manifest)
        if request.full_url.endswith("stable.json.sig"):
            return Response(signature)
        return Response(installer)

    monkeypatch.setattr(updater, "TRUSTED_UPDATE_KEYS", trusted_keys or {TEST_KEY_ID: TEST_PUBLIC_B64})
    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    monkeypatch.delenv("TIKTOK_REPORT_UPDATE_FEED_URL", raising=False)
    return seen_headers


def test_sign_update_feed_writes_byte_stable_lf_files(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"installer")
    output_dir = tmp_path / "feed"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sign_update_feed.py",
            "--version",
            "1.2.1",
            "--installer",
            str(installer),
            "--asset-url",
            "https://github.com/anhtahaylove/tiktok-affiliate-report-updates/releases/download/v1.2.1/TikTokAffiliateReportSetup-v1.2.1.exe",
            "--release-url",
            "https://github.com/anhtahaylove/tiktok-affiliate-report-updates/releases/tag/v1.2.1",
            "--key-id",
            TEST_KEY_ID,
            "--output-dir",
            str(output_dir),
            "--published-at",
            "2026-08-04T00:00:00Z",
            "--private-key-b64",
            base64.b64encode(bytes(range(1, 33))).decode("ascii"),
        ],
    )

    assert sign_update_feed.main() == 0
    manifest = (output_dir / "stable.json").read_bytes()
    signature = (output_dir / "stable.json.sig").read_bytes()
    assert b"\r" not in manifest + signature
    monkeypatch.setattr(updater, "TRUSTED_UPDATE_KEYS", {TEST_KEY_ID: TEST_PUBLIC_B64})
    assert updater.verify_update_manifest_bytes(manifest, signature)["version"] == "1.2.1"


def test_check_and_download_update_with_verified_signed_public_feed(tmp_path, monkeypatch):
    manifest, signature, installer = stable_feed()
    seen_headers = install_feed(monkeypatch, manifest, signature, installer)

    checked = updater.check_for_update(current_version="1.1.1", token="ignored")
    progress = []
    downloaded = updater.download_latest_update(tmp_path, current_version="1.1.1", token="ignored", progress_callback=lambda done, total: progress.append((done, total)))

    assert set(json.loads(manifest)) == {"schema", "app_id", "channel", "version", "published_at", "release_url", "installer"}
    assert checked["available"] is True
    assert checked["installable"] is True
    assert checked["source_repo"] == "anhtahaylove/tiktok-affiliate-report-updates"
    assert downloaded["sha256"] == hashlib.sha256(installer).hexdigest().upper()
    assert Path(downloaded["installer_path"]).read_bytes() == installer
    assert progress == [(len(installer), len(installer))]
    assert all("Authorization" not in headers for headers in seen_headers)


def test_download_rejects_tampered_manifest_signature(tmp_path, monkeypatch):
    manifest, signature, installer = stable_feed()
    tampered = manifest.replace(b'"channel":"stable"', b'"channel":"beta"')
    install_feed(monkeypatch, tampered, signature, installer)

    with pytest.raises(updater.UpdateError, match="Chữ ký"):
        updater.download_latest_update(tmp_path, current_version="1.1.1")
    assert not list(tmp_path.rglob("*.exe"))


def test_signing_key_rotation_accepts_a_second_pinned_key(monkeypatch):
    manifest, signature, installer = stable_feed(signing_key=NEXT_PRIVATE, key_id="next-key")
    install_feed(
        monkeypatch,
        manifest,
        signature,
        installer,
        trusted_keys={TEST_KEY_ID: TEST_PUBLIC_B64, "next-key": NEXT_PUBLIC_B64},
    )

    assert updater.check_for_update(current_version="1.1.1")["available"] is True


def test_signed_feed_rejects_an_unpinned_key_id(monkeypatch):
    manifest, signature, installer = stable_feed(key_id="unknown-key")
    install_feed(monkeypatch, manifest, signature, installer)

    with pytest.raises(updater.UpdateError, match="key_id"):
        updater.check_for_update(current_version="1.1.1")


def test_download_rejects_installer_hash_mismatch(tmp_path, monkeypatch):
    manifest, signature, _installer = stable_feed(installer=b"clean")
    install_feed(monkeypatch, manifest, signature, b"xxxxx")

    with pytest.raises(updater.UpdateError, match="SHA-256"):
        updater.download_latest_update(tmp_path, current_version="1.1.1")
    assert not list(tmp_path.rglob("*.exe"))


def test_download_rejects_downgrade_or_same_version(tmp_path, monkeypatch):
    manifest, signature, installer = stable_feed(version="1.1.1")
    install_feed(monkeypatch, manifest, signature, installer)

    with pytest.raises(updater.UpdateError, match="phiên bản mới nhất"):
        updater.download_latest_update(tmp_path, current_version="1.1.1")
    assert not list(tmp_path.rglob("*.exe"))


def test_manifest_rejects_non_https_bad_filename_size_and_tag(monkeypatch):
    manifest, signature, installer = stable_feed(release_url="http://example.test/release")
    install_feed(monkeypatch, manifest, signature, installer)
    with pytest.raises(updater.UpdateError, match="Release URL"):
        updater.check_for_update(current_version="1.1.1")

    manifest, signature, installer = stable_feed(name="evil.exe")
    install_feed(monkeypatch, manifest, signature, installer)
    with pytest.raises(updater.UpdateError, match="Tên installer"):
        updater.check_for_update(current_version="1.1.1")

    manifest, signature, installer = stable_feed(
        installer_info={
            "name": "TikTokAffiliateReportSetup-v1.2.1.exe",
            "url": "https://example.test/TikTokAffiliateReportSetup-v1.2.1.exe",
            "size": 0,
            "sha256": "0" * 64,
        }
    )
    install_feed(monkeypatch, manifest, signature, installer)
    with pytest.raises(updater.UpdateError, match="Kích thước"):
        updater.check_for_update(current_version="1.1.1")

    manifest, signature, installer = stable_feed(
        installer_info={
            "name": "TikTokAffiliateReportSetup-v1.2.1.exe",
            "url": "https://example.test/TikTokAffiliateReportSetup-v1.2.1.exe",
            "size": updater.MAX_INSTALLER_BYTES + 1,
            "sha256": "0" * 64,
        }
    )
    install_feed(monkeypatch, manifest, signature, installer)
    with pytest.raises(updater.UpdateError, match="Kích thước"):
        updater.check_for_update(current_version="1.1.1")

    manifest, signature, installer = stable_feed(app_id="other-app")
    install_feed(monkeypatch, manifest, signature, installer)
    with pytest.raises(updater.UpdateError, match="app_id"):
        updater.check_for_update(current_version="1.1.1")

    manifest, signature, installer = stable_feed(channel="beta")
    install_feed(monkeypatch, manifest, signature, installer)
    with pytest.raises(updater.UpdateError, match="channel"):
        updater.check_for_update(current_version="1.1.1")


def test_dev_feed_override_is_not_allowed_when_frozen(monkeypatch):
    monkeypatch.setenv("TIKTOK_REPORT_UPDATE_FEED_URL", "https://example.test/stable.json")
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)

    with pytest.raises(updater.UpdateError, match="Không cho phép"):
        updater.check_for_update(current_version="1.1.1")


def test_dev_feed_override_works_only_for_non_frozen_builds(monkeypatch):
    monkeypatch.setenv("TIKTOK_REPORT_UPDATE_FEED_URL", "https://example.test/custom/stable.json")
    monkeypatch.setattr(updater.sys, "frozen", False, raising=False)
    assert updater.configured_feed_url() == "https://example.test/custom/stable.json"


def test_public_update_path_does_not_use_github_token_or_gh_cli(monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    for name in ("TIKTOK_REPORT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "TIKTOK_REPORT_USE_GH_CLI"):
        monkeypatch.setenv(name, "secret")

    assert updater.github_token() is None
    with pytest.raises(updater.UpdateError, match="không dùng GitHub token"):
        updater._latest_release("https://example.test/stable.json", token="secret")


def test_windows_update_helper_waits_verifies_installs_and_restarts(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
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

    updater._launch_update_helper(installer, expected, tmp_path / "updater.log", tmp_path / "update-status.json", "1.2.1", installer.stat().st_size)

    helper_path = installer.parent / "install-update.ps1"
    helper = helper_path.read_text(encoding="utf-8-sig")
    assert "Write-UpdateStatus 'waiting_for_exit'" in helper
    assert "[System.Diagnostics.Process]::GetProcessById($ParentPid)" in helper
    assert "[System.Security.Cryptography.SHA256]::Create()" in helper
    assert "Start-Child $Installer" in helper
    assert "Start-Child $AppExe" in helper
    # $ParentPid only tracks the PyInstaller onefile child; its bootloader parent can still hold
    # $AppExe open briefly after that PID exits, so we must also wait for the file handle itself
    # to free up before invoking /CLOSEAPPLICATIONS, or Setup aborts with exit code 5.
    assert "function Wait-FileUnlocked" in helper
    assert "Wait-FileUnlocked $AppExe 15000" in helper
    assert helper.index("Wait-FileUnlocked $AppExe") > helper.index("$parentExited = $true")
    assert helper.index("Wait-FileUnlocked $AppExe") < helper.index("Start-Child $Installer")
    for forbidden in ("Wait-Process", "Get-FileHash", "Get-Process", "Start-Process", "Remove-Item"):
        assert forbidden not in helper
    assert captured["args"][0] == str(powershell)
    assert captured["args"][captured["args"].index("-File") + 1] == str(helper_path)
    assert captured["args"][captured["args"].index("-ExpectedSha256") + 1] == expected
    assert captured["kwargs"]["cwd"] == installer.parent
    assert captured["kwargs"]["creationflags"] == 48
    assert captured["kwargs"]["stdout"] is captured["kwargs"]["stderr"]


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_windows_update_helper_replaces_existing_status_file(tmp_path):
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"not-an-installer")
    helper = tmp_path / "install-update.ps1"
    helper.write_text(updater._powershell_helper_script(), encoding="utf-8-sig")
    status_path = tmp_path / "update-status.json"
    updater.write_update_status(
        status_path,
        phase="verifying",
        target_version="1.2.1",
        bytes_downloaded=installer.stat().st_size,
        bytes_total=installer.stat().st_size,
    )

    result = subprocess.run(
        [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            "-ParentPid",
            str(2_147_483_647),
            "-Installer",
            str(installer),
            "-ExpectedSha256",
            "0" * 64,
            "-AppExe",
            str(tmp_path / "TikTokAffiliateReport.exe"),
            "-LogPath",
            str(tmp_path / "updater.log"),
            "-InstallerLog",
            str(tmp_path / "installer.log"),
            "-StatusPath",
            str(status_path),
            "-TargetVersion",
            "1.2.1",
            "-InstallerSize",
            str(installer.stat().st_size),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    status = updater.read_update_status(status_path)
    assert status["phase"] == "failed"
    assert "SHA-256" in status["error"]
    assert "Updater helper started." in (tmp_path / "updater.log").read_text(encoding="utf-8")
    assert not list(tmp_path.glob("update-status.json.*.tmp"))


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows file locking semantics")
def test_wait_file_unlocked_detects_a_file_still_held_open_by_another_process(tmp_path):
    # Regression test for the v1.2.7 update failure: $ParentPid only tracks the PyInstaller
    # onefile child, so WaitForExit($ParentPid) can return while the bootloader parent still
    # holds $AppExe open, and Setup's /CLOSEAPPLICATIONS then aborts (exit code 5). Exercise the
    # real Wait-FileUnlocked function (extracted from the generated helper) against actual
    # Windows file-sharing semantics rather than mocking them.
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    helper_source = updater._powershell_helper_script()
    match = re.search(r"function Wait-FileUnlocked\b.*?\n}\n", helper_source, re.DOTALL)
    assert match, "Wait-FileUnlocked function not found in generated helper script"
    probe = tmp_path / "probe.ps1"
    probe.write_text(match.group(0) + "\nWrite-Output (Wait-FileUnlocked $args[0] ([int]$args[1]))\n", encoding="utf-8-sig")
    target = tmp_path / "TikTokAffiliateReport.exe"
    target.write_bytes(b"app")

    def run_probe(timeout_ms):
        return subprocess.run(
            [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe), str(target), str(timeout_ms)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    unlocked = run_probe(5000)
    assert unlocked.stdout.strip() == "True", unlocked.stderr

    with open(target, "rb"):
        started = time.monotonic()
        locked = run_probe(300)
        elapsed = time.monotonic() - started
    assert locked.stdout.strip() == "False", locked.stderr
    assert elapsed < 5, f"Wait-FileUnlocked should give up around its own timeout, took {elapsed:.1f}s"


def test_scheduled_installer_rechecks_sha256_before_launch(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"tampered")
    log_path = tmp_path / "updater.log"
    shutdown = threading.Event()
    monkeypatch.setattr(updater, "_windows_frozen", lambda: True)

    with pytest.raises(updater.UpdateError, match="đã thay đổi"):
        updater.schedule_installer(installer, "0" * 64, log_path, shutdown.set, status_path=tmp_path / "update-status.json", target_version="1.2.1", delay_seconds=0)

    assert not shutdown.is_set()


def test_update_status_is_atomic_validated_and_normalizes_installed(tmp_path):
    status_path = tmp_path / "update-status.json"

    assert updater.read_update_status(status_path)["phase"] == "idle"
    written = updater.write_update_status(
        status_path,
        phase="waiting_for_exit",
        target_version="1.2.1",
        bytes_downloaded=7,
        bytes_total=9,
    )

    assert json.loads(status_path.read_text(encoding="utf-8")) == written
    assert updater.read_update_status(status_path, current_version="1.2.0")["phase"] == "waiting_for_exit"
    assert updater.read_update_status(status_path, current_version="1.2.1")["phase"] == "installed"

    status_path.write_text("{}", encoding="utf-8")
    with pytest.raises(updater.UpdateError, match="schema"):
        updater.read_update_status(status_path)


def test_schedule_installer_waits_for_helper_handshake_before_shutdown(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"installer")
    expected = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    status_path = tmp_path / "update-status.json"
    shutdown = threading.Event()

    def fake_launch(installer_path, expected_sha256, log_path, status, target_version, installer_size):
        assert installer_path == installer.resolve()
        assert expected_sha256 == expected
        assert installer_size == len(b"installer")
        updater.write_update_status(status, phase="waiting_for_exit", target_version=target_version, bytes_downloaded=installer_size, bytes_total=installer_size)

    monkeypatch.setattr(updater, "_windows_frozen", lambda: True)
    monkeypatch.setattr(updater, "_launch_update_helper", fake_launch)

    updater.schedule_installer(installer, expected, tmp_path / "updater.log", shutdown.set, status_path=status_path, target_version="1.2.1", delay_seconds=0)

    shutdown.wait(1)
    assert shutdown.is_set()


def test_schedule_installer_fails_without_helper_handshake(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"installer")
    expected = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    shutdown = threading.Event()

    monkeypatch.setattr(updater, "_launch_update_helper", lambda *_args: None)
    monkeypatch.setattr(updater, "_wait_for_helper_handshake", lambda *_args: (_ for _ in ()).throw(updater.UpdateError("no handshake")))

    with pytest.raises(updater.UpdateError, match="no handshake"):
        updater.schedule_installer(installer, expected, tmp_path / "updater.log", shutdown.set, status_path=tmp_path / "update-status.json", target_version="1.2.1", delay_seconds=0)
    assert not shutdown.is_set()


def test_version_validation():
    with pytest.raises(updater.UpdateError, match="Phiên bản"):
        updater._parse_version("1.2")
