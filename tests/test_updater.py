from __future__ import annotations

import base64
import functools
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
from urllib.error import URLError

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
    bootstrap_info = overrides.pop("bootstrap_info", None)
    manifest = {
        "schema": updater.UPDATE_SCHEMA,
        "app_id": updater.UPDATE_APP_ID,
        "channel": updater.UPDATE_CHANNEL,
        "version": version,
        "published_at": "2026-08-04T00:00:00Z",
        "release_url": f"https://github.com/anhtahaylove/tiktok-affiliate-report/releases/tag/v{version}",
        "installer": installer_info or {
            "name": name,
            "url": f"https://github.com/anhtahaylove/tiktok-affiliate-report/releases/download/v{version}/{name}",
            "size": len(installer),
            "sha256": hashlib.sha256(installer).hexdigest().upper(),
        },
        "bootstrap": bootstrap_info or {
            "protocol": updater.UPDATE_BOOTSTRAP_PROTOCOL,
            "version": updater.UPDATE_BOOTSTRAP_VERSION,
            "name": updater.UPDATE_BOOTSTRAP_NAME,
            "url": f"https://github.com/anhtahaylove/tiktok-affiliate-report/releases/download/v{version}/{updater.UPDATE_BOOTSTRAP_NAME}",
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


def install_feed(
    monkeypatch,
    manifest: bytes,
    signature: bytes,
    installer: bytes = b"installer",
    trusted_keys=None,
    *,
    bootstrap: bytes | None = None,
):
    seen_headers = []

    def fake_urlopen(request, timeout):
        seen_headers.append(dict(request.header_items()))
        if request.full_url.endswith("stable.json"):
            return Response(manifest)
        if request.full_url.endswith("stable.json.sig"):
            return Response(signature)
        if request.full_url.endswith(".ps1"):
            return Response(installer if bootstrap is None else bootstrap)
        return Response(installer)

    monkeypatch.setattr(updater, "TRUSTED_UPDATE_KEYS", trusted_keys or {TEST_KEY_ID: TEST_PUBLIC_B64})
    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    monkeypatch.delenv("TIKTOK_REPORT_UPDATE_FEED_URL", raising=False)
    return seen_headers


def write_bootstrap_asset(tmp_path: Path, content: bytes = b"bootstrap") -> tuple[Path, str]:
    path = tmp_path / updater.UPDATE_BOOTSTRAP_NAME
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest().upper()


def test_sign_update_feed_writes_byte_stable_lf_files(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"installer")
    bootstrap = tmp_path / "TikTokAffiliateUpdater-v1.0.0.ps1"
    bootstrap.write_bytes(b"bootstrap")
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
            "--bootstrap",
            str(bootstrap),
            "--asset-url",
            "https://github.com/anhtahaylove/tiktok-affiliate-report/releases/download/v1.2.1/TikTokAffiliateReportSetup-v1.2.1.exe",
            "--bootstrap-url",
            "https://github.com/anhtahaylove/tiktok-affiliate-report/releases/download/v1.2.1/TikTokAffiliateUpdater-v1.0.0.ps1",
            "--release-url",
            "https://github.com/anhtahaylove/tiktok-affiliate-report/releases/tag/v1.2.1",
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
    verified = updater.verify_update_manifest_bytes(manifest, signature)
    assert verified["version"] == "1.2.1"
    assert verified["bootstrap"] == {
        "protocol": 1,
        "version": "1.0.0",
        "name": "TikTokAffiliateUpdater-v1.0.0.ps1",
        "url": "https://github.com/anhtahaylove/tiktok-affiliate-report/releases/download/v1.2.1/TikTokAffiliateUpdater-v1.0.0.ps1",
        "size": len(b"bootstrap"),
        "sha256": hashlib.sha256(b"bootstrap").hexdigest().upper(),
    }


def test_check_and_download_update_with_verified_signed_public_feed(tmp_path, monkeypatch):
    manifest, signature, installer = stable_feed()
    seen_headers = install_feed(monkeypatch, manifest, signature, installer)

    checked = updater.check_for_update(current_version="1.1.1", token="ignored")
    progress = []
    downloaded = updater.download_latest_update(tmp_path, current_version="1.1.1", token="ignored", progress_callback=lambda done, total: progress.append((done, total)))

    assert set(json.loads(manifest)) == {"schema", "app_id", "channel", "version", "published_at", "release_url", "installer", "bootstrap"}
    assert checked["available"] is True
    assert checked["installable"] is True
    assert checked["source_repo"] == "anhtahaylove/tiktok-affiliate-report"
    assert downloaded["sha256"] == hashlib.sha256(installer).hexdigest().upper()
    assert Path(downloaded["installer_path"]).read_bytes() == installer
    assert downloaded["bootstrap_protocol"] == 1
    assert downloaded["bootstrap_sha256"] == hashlib.sha256(installer).hexdigest().upper()
    assert Path(downloaded["bootstrap_path"]).read_bytes() == installer
    assert progress == [(len(installer), len(installer) * 2), (len(installer) * 2, len(installer) * 2)]
    assert all("Authorization" not in headers for headers in seen_headers)


def test_manifest_accepts_new_bootstrap_version_within_supported_protocol(monkeypatch):
    bootstrap = b"future-bootstrap"
    bootstrap_version = "1.1.0"
    bootstrap_name = f"TikTokAffiliateUpdater-v{bootstrap_version}.ps1"
    manifest, signature, installer = stable_feed(
        bootstrap_info={
            "protocol": updater.UPDATE_BOOTSTRAP_PROTOCOL,
            "version": bootstrap_version,
            "name": bootstrap_name,
            "url": (
                "https://github.com/anhtahaylove/tiktok-affiliate-report/releases/"
                f"download/v1.2.1/{bootstrap_name}"
            ),
            "size": len(bootstrap),
            "sha256": hashlib.sha256(bootstrap).hexdigest().upper(),
        }
    )
    install_feed(monkeypatch, manifest, signature, installer)

    checked = updater.check_for_update(current_version="1.1.1")

    assert checked["bootstrap_version"] == bootstrap_version
    assert checked["bootstrap_protocol"] == updater.UPDATE_BOOTSTRAP_PROTOCOL


def test_old_feed_without_bootstrap_remains_readable_for_rollback(monkeypatch):
    manifest, _signature, installer = stable_feed(version="2.0.6")
    raw = json.loads(manifest)
    raw.pop("bootstrap")
    payload = (json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n").encode()
    signature = json.dumps(
        {"key_id": TEST_KEY_ID, "signature": base64.b64encode(TEST_PRIVATE.sign(payload)).decode("ascii")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    install_feed(monkeypatch, payload, signature, installer)

    checked = updater.check_for_update(current_version="2.0.7")

    assert checked["available"] is False
    assert checked["installable"] is False
    assert "bootstrap_protocol" not in checked


def test_newer_feed_without_bootstrap_is_not_automatically_installable(tmp_path, monkeypatch):
    manifest, _signature, installer = stable_feed(version="2.0.8")
    raw = json.loads(manifest)
    raw.pop("bootstrap")
    payload = (json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n").encode()
    signature = json.dumps(
        {"key_id": TEST_KEY_ID, "signature": base64.b64encode(TEST_PRIVATE.sign(payload)).decode("ascii")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    install_feed(monkeypatch, payload, signature, installer)

    checked = updater.check_for_update(current_version="2.0.7")

    assert checked["available"] is True
    assert checked["installable"] is False
    with pytest.raises(updater.UpdateError, match="thiếu updater bootstrap"):
        updater.download_latest_update(tmp_path, current_version="2.0.7")


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


def test_download_rejects_bootstrap_hash_mismatch_and_removes_partial_bundle(tmp_path, monkeypatch):
    manifest, signature, installer = stable_feed(installer=b"clean")
    install_feed(monkeypatch, manifest, signature, installer, bootstrap=b"dirty")

    with pytest.raises(updater.UpdateError, match="bootstrap"):
        updater.download_latest_update(tmp_path, current_version="1.1.1")

    assert not list(tmp_path.rglob("*.exe"))
    assert not list(tmp_path.rglob("*.ps1"))


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


@pytest.mark.parametrize(
    ("bootstrap_info", "message"),
    [
        ({"protocol": 2, "version": "1.0.0", "name": "TikTokAffiliateUpdater-v1.0.0.ps1", "url": "https://example.test/TikTokAffiliateUpdater-v1.0.0.ps1", "size": 1, "sha256": "0" * 64}, "protocol"),
        ({"protocol": 1, "version": "1.0.0", "name": "evil.ps1", "url": "https://example.test/evil.ps1", "size": 1, "sha256": "0" * 64}, "Tên hoặc phiên bản"),
        ({"protocol": 1, "version": "1.0.0", "name": "TikTokAffiliateUpdater-v1.0.0.ps1", "url": "https://example.test/TikTokAffiliateUpdater-v1.0.0.ps1", "size": 0, "sha256": "0" * 64}, "Kích thước"),
        ({"protocol": 1, "version": "1.0.0", "name": "TikTokAffiliateUpdater-v1.0.0.ps1", "url": "https://example.test/TikTokAffiliateUpdater-v1.0.0.ps1", "size": updater.MAX_BOOTSTRAP_BYTES + 1, "sha256": "0" * 64}, "Kích thước"),
        ({"protocol": 1, "version": "1.0.0", "name": "TikTokAffiliateUpdater-v1.0.0.ps1", "url": "http://example.test/TikTokAffiliateUpdater-v1.0.0.ps1", "size": 1, "sha256": "0" * 64}, "URL"),
        ({"protocol": 1, "version": "1.0.0", "name": "TikTokAffiliateUpdater-v1.0.0.ps1", "url": "https://example.test/TikTokAffiliateUpdater-v1.0.0.ps1", "size": 1, "sha256": "bad"}, "SHA-256"),
    ],
)
def test_manifest_rejects_missing_or_invalid_bootstrap(monkeypatch, bootstrap_info, message):
    manifest, signature, installer = stable_feed(bootstrap_info=bootstrap_info)
    install_feed(monkeypatch, manifest, signature, installer)
    with pytest.raises(updater.UpdateError, match=message):
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
    bootstrap, bootstrap_sha256 = write_bootstrap_asset(
        tmp_path,
        Path("packaging/TikTokAffiliateUpdater-v1.0.0.ps1").read_bytes(),
    )
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

    instance_state = tmp_path / "instance.json"
    updater._launch_update_bootstrap(
        installer_path=installer,
        expected_sha256=expected,
        bootstrap_path=bootstrap,
        expected_bootstrap_sha256=bootstrap_sha256,
        bootstrap_protocol=updater.UPDATE_BOOTSTRAP_PROTOCOL,
        bootstrap_version=updater.UPDATE_BOOTSTRAP_VERSION,
        log_path=tmp_path / "updater.log",
        status_path=tmp_path / "update-status.json",
        target_version="1.2.1",
        installer_size=installer.stat().st_size,
        instance_state_path=instance_state,
        attempt_id="a" * 32,
        ack_path=tmp_path / "bootstrap-ack.json",
    )

    helper = bootstrap.read_text(encoding="utf-8-sig")
    assert "Write-UpdateStatus 'waiting_for_exit'" in helper
    assert "[System.Diagnostics.Process]::GetProcessById($ParentPid)" in helper
    assert "[System.Security.Cryptography.SHA256]::Create()" in helper
    assert "Start-Child $Installer" in helper
    assert "Start-Child $AppExe" in helper
    # Waiting for the tracked PID is not sufficient if another app-owned process still holds the
    # executable; verify the file handle before invoking /CLOSEAPPLICATIONS.
    assert "function Wait-FileUnlocked" in helper
    assert "Wait-FileUnlocked $AppExe 15000" in helper
    assert helper.index("Wait-FileUnlocked $AppExe") > helper.index("$parentExited = $true")
    assert helper.index("Wait-FileUnlocked $AppExe") < helper.index("Start-Child $Installer")
    # Start-Child launching the app back up isn't proof it's usable, nên vẫn phải chờ /health thật.
    # Bản onedir không giải nén runtime ra %TEMP% nữa nên lần mở đầu nhanh như mọi lần khác.
    assert "function Wait-AppHealthy" in helper
    assert "Wait-AppHealthy $InstanceStatePath $TargetVersion 90000" in helper
    restarting_index = helper.index("Write-UpdateStatus 'restarting'")
    first_start_child_index = helper.index("Start-Child $AppExe", restarting_index)
    health_index = helper.index("Wait-AppHealthy $InstanceStatePath $TargetVersion 90000")
    assert first_start_child_index < health_index
    assert helper.index("Write-UpdateStatus 'installed' $null", health_index) > health_index
    assert "Target app did not report the expected version and healthy state within 90s." in helper
    assert "Write-UpdateStatus 'installed' 'Đã cài xong" not in helper
    assert "Write-UpdateStatus 'restarting' $failure" in helper
    # Chỉ mở app đúng MỘT lần sau khi cài. Mở lần hai khi lần đầu chưa phản hồi là thứ đã sinh ra
    # hộp thoại "Failed to load Python DLL": hai tiến trình cùng giải nén tranh nhau đĩa và AV.
    assert helper.count("Start-Child $AppExe") == 2  # một lần sau khi cài, một lần khi cài lỗi
    assert "retrying launch once" not in helper
    for forbidden in ("Wait-Process", "Get-FileHash", "Get-Process", "Start-Process", "Remove-Item"):
        assert forbidden not in helper
    assert captured["args"][0] == str(powershell)
    assert captured["args"][captured["args"].index("-File") + 1] == str(bootstrap)
    assert captured["args"][captured["args"].index("-ExpectedSha256") + 1] == expected
    assert captured["args"][captured["args"].index("-InstanceStatePath") + 1] == str(instance_state)
    assert captured["args"][captured["args"].index("-BootstrapProtocol") + 1] == "1"
    assert captured["args"][captured["args"].index("-BootstrapVersion") + 1] == "1.0.0"
    assert captured["args"][captured["args"].index("-AttemptId") + 1] == "a" * 32
    assert captured["kwargs"]["cwd"] == installer.parent
    assert captured["kwargs"]["creationflags"] == 48
    assert captured["kwargs"]["stdout"] is captured["kwargs"]["stderr"]


def test_launch_rejects_bootstrap_changed_after_download(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v2.0.7.exe"
    installer.write_bytes(b"installer")
    bootstrap, expected_bootstrap_sha256 = write_bootstrap_asset(tmp_path, b"verified-bootstrap")
    bootstrap.write_bytes(b"tampered-bootstrap")
    monkeypatch.setattr(updater, "_windows_frozen", lambda: True)

    with pytest.raises(updater.UpdateError, match="bootstrap đã thay đổi"):
        updater._launch_update_bootstrap(
            installer_path=installer,
            expected_sha256=hashlib.sha256(installer.read_bytes()).hexdigest().upper(),
            bootstrap_path=bootstrap,
            expected_bootstrap_sha256=expected_bootstrap_sha256,
            bootstrap_protocol=1,
            bootstrap_version="1.0.0",
            log_path=tmp_path / "updater.log",
            status_path=tmp_path / "update-status.json",
            target_version="2.0.7",
            installer_size=installer.stat().st_size,
            instance_state_path=tmp_path / "instance.json",
            attempt_id="a" * 32,
            ack_path=tmp_path / "bootstrap-ack.json",
        )


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_windows_update_helper_replaces_existing_status_file(tmp_path):
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"not-an-installer")
    helper = Path("packaging/TikTokAffiliateUpdater-v1.0.0.ps1").resolve()
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
            "-InstanceStatePath",
            str(tmp_path / "instance.json"),
            "-BootstrapProtocol",
            "1",
            "-BootstrapVersion",
            "1.0.0",
            "-AttemptId",
            "a" * 32,
            "-AckPath",
            str(tmp_path / "bootstrap-ack.json"),
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
    assert "Updater bootstrap protocol 1 started." in (tmp_path / "updater.log").read_text(encoding="utf-8")
    ack = json.loads((tmp_path / "bootstrap-ack.json").read_text(encoding="utf-8"))
    assert ack == {
        "attempt_id": "a" * 32,
        "bootstrap_version": "1.0.0",
        "phase": "ready",
        "protocol": 1,
        "schema": updater.BOOTSTRAP_ACK_SCHEMA,
        "target_version": "1.2.1",
        "updated_at": ack["updated_at"],
    }
    assert not list(tmp_path.glob("update-status.json.*.tmp"))


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_windows_bootstrap_executes_a_newer_asset_version_on_same_protocol(tmp_path):
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    helper = tmp_path / "TikTokAffiliateUpdater-v1.1.0.ps1"
    helper.write_bytes(Path("packaging/TikTokAffiliateUpdater-v1.0.0.ps1").read_bytes())
    installer = tmp_path / "TikTokAffiliateReportSetup-v2.0.8.exe"
    installer.write_bytes(b"not-an-installer")
    status_path = tmp_path / "update-status.json"
    ack_path = tmp_path / "bootstrap-ack.json"

    result = subprocess.run(
        [
            str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(helper), "-ParentPid", str(2_147_483_647), "-Installer", str(installer),
            "-ExpectedSha256", "0" * 64, "-AppExe", str(tmp_path / "TikTokAffiliateReport.exe"),
            "-LogPath", str(tmp_path / "updater.log"), "-InstallerLog", str(tmp_path / "installer.log"),
            "-StatusPath", str(status_path), "-TargetVersion", "2.0.8", "-InstallerSize", str(installer.stat().st_size),
            "-InstanceStatePath", str(tmp_path / "instance.json"), "-BootstrapProtocol", "1",
            "-BootstrapVersion", "1.1.0", "-AttemptId", "b" * 32, "-AckPath", str(ack_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert updater.read_update_status(status_path)["phase"] == "failed"
    ack = json.loads(ack_path.read_text(encoding="utf-8"))
    assert ack["bootstrap_version"] == "1.1.0"
    assert ack["protocol"] == 1


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows file locking semantics")
def test_wait_file_unlocked_detects_a_file_still_held_open_by_another_process(tmp_path):
    # Regression test for the v1.2.7 update failure: $ParentPid only tracks the PyInstaller
    # onefile child, so WaitForExit($ParentPid) can return while the bootloader parent still
    # holds $AppExe open, and Setup's /CLOSEAPPLICATIONS then aborts (exit code 5). Exercise the
    # real Wait-FileUnlocked function (extracted from the generated helper) against actual
    # Windows file-sharing semantics rather than mocking them.
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    helper_source = Path("packaging/TikTokAffiliateUpdater-v1.0.0.ps1").read_text(encoding="utf-8-sig")
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


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell + real sockets")
def test_wait_app_healthy_polls_instance_state_and_health_endpoint(tmp_path):
    # Regression test for the v1.2.11 restart hang: Start-Child launching the relaunched app is
    # not proof it's usable — the relaunch can stall for several seconds right after install.
    # Exercise the real Wait-AppHealthy/Test-Health functions against an actual HTTP listener and
    # actual instance.json contents, not mocks.
    import http.server

    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    helper_source = Path("packaging/TikTokAffiliateUpdater-v1.0.0.ps1").read_text(encoding="utf-8-sig")
    health_match = re.search(r"function Test-Health\b.*?\n}\n", helper_source, re.DOTALL)
    wait_match = re.search(r"function Wait-AppHealthy\b.*?\n}\n", helper_source, re.DOTALL)
    assert health_match, "Test-Health function not found in generated helper script"
    assert wait_match, "Wait-AppHealthy function not found in generated helper script"
    probe = tmp_path / "probe.ps1"
    probe.write_text(health_match.group(0) + "\n" + wait_match.group(0) + "\nWrite-Output (Wait-AppHealthy $args[0] $args[1] ([int]$args[2]))\n", encoding="utf-8-sig")
    state_path = tmp_path / "instance.json"

    def run_probe(timeout_ms):
        return subprocess.run(
            [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe), str(state_path), "2.0.7", str(timeout_ms)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    # No instance.json yet at all -> gives up around its own timeout, no exception.
    started = time.monotonic()
    missing = run_probe(300)
    elapsed = time.monotonic() - started
    assert missing.stdout.strip() == "False", missing.stderr
    assert elapsed < 5

    class HealthHandler(http.server.BaseHTTPRequestHandler):
        app_version = "2.0.7"

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "app_version": self.app_version}).encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        state_path.write_text(json.dumps({"pid": 1234, "url": url, "app_version": "2.0.6"}), encoding="utf-8")
        wrong_version = run_probe(300)
        assert wrong_version.stdout.strip() == "False", wrong_version.stderr
        state_path.write_text(json.dumps({"pid": 1234, "url": url, "app_version": "2.0.7"}), encoding="utf-8")
        healthy = run_probe(5000)
        assert healthy.stdout.strip() == "True", healthy.stderr
        HealthHandler.app_version = "2.0.6"
        wrong_health_version = run_probe(300)
        assert wrong_health_version.stdout.strip() == "False", wrong_health_version.stderr
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_scheduled_installer_rechecks_sha256_before_launch(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"tampered")
    log_path = tmp_path / "updater.log"
    shutdown = threading.Event()
    bootstrap, bootstrap_sha256 = write_bootstrap_asset(tmp_path)
    monkeypatch.setattr(updater, "_windows_frozen", lambda: True)

    with pytest.raises(updater.UpdateError, match="đã thay đổi"):
        updater.schedule_installer(
            installer,
            "0" * 64,
            log_path,
            shutdown.set,
            status_path=tmp_path / "update-status.json",
            target_version="1.2.1",
            bootstrap_path=bootstrap,
            bootstrap_sha256=bootstrap_sha256,
            bootstrap_protocol=1,
            bootstrap_version="1.0.0",
            delay_seconds=0,
        )

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

    updater.write_update_status(
        status_path,
        phase="restarting",
        target_version="1.2.1",
        bytes_downloaded=9,
        bytes_total=9,
    )
    assert updater.read_update_status(status_path, current_version="1.2.0")["phase"] == "restarting"
    assert updater.read_update_status(status_path, current_version="1.2.2")["phase"] == "installed"
    assert json.loads(status_path.read_text(encoding="utf-8"))["phase"] == "restarting"

    updater.write_update_status(
        status_path,
        phase="installed",
        target_version="1.2.1",
        bytes_downloaded=9,
        bytes_total=9,
        error="App did not report healthy within 90s.",
    )
    unresolved = updater.read_update_status(status_path, current_version="1.2.0")
    resolved = updater.read_update_status(status_path, current_version="1.2.1")
    assert unresolved["error"] == "App did not report healthy within 90s."
    assert resolved["phase"] == "installed"
    assert resolved["error"] is None
    assert json.loads(status_path.read_text(encoding="utf-8"))["error"] == "App did not report healthy within 90s."

    status_path.write_text("{}", encoding="utf-8")
    with pytest.raises(updater.UpdateError, match="schema"):
        updater.read_update_status(status_path)


def test_schedule_installer_waits_for_helper_handshake_before_shutdown(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"installer")
    expected = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    status_path = tmp_path / "update-status.json"
    shutdown = threading.Event()
    bootstrap, bootstrap_sha256 = write_bootstrap_asset(tmp_path)

    def fake_launch(**kwargs):
        assert kwargs["installer_path"] == installer.resolve()
        assert kwargs["expected_sha256"] == expected
        assert kwargs["bootstrap_path"] == bootstrap.resolve()
        assert kwargs["expected_bootstrap_sha256"] == bootstrap_sha256
        assert kwargs["installer_size"] == len(b"installer")
        Path(kwargs["ack_path"]).write_text(
            json.dumps(
                {
                    "schema": updater.BOOTSTRAP_ACK_SCHEMA,
                    "phase": "ready",
                    "attempt_id": kwargs["attempt_id"],
                    "protocol": 1,
                    "bootstrap_version": "1.0.0",
                    "target_version": kwargs["target_version"],
                }
            ),
            encoding="utf-8",
        )
        updater.write_update_status(kwargs["status_path"], phase="waiting_for_exit", target_version=kwargs["target_version"], bytes_downloaded=kwargs["installer_size"], bytes_total=kwargs["installer_size"])

    monkeypatch.setattr(updater, "_windows_frozen", lambda: True)
    monkeypatch.setattr(updater, "_launch_update_bootstrap", fake_launch)

    updater.schedule_installer(
        installer,
        expected,
        tmp_path / "updater.log",
        shutdown.set,
        status_path=status_path,
        target_version="1.2.1",
        bootstrap_path=bootstrap,
        bootstrap_sha256=bootstrap_sha256,
        bootstrap_protocol=1,
        bootstrap_version="1.0.0",
        delay_seconds=0,
    )

    shutdown.wait(1)
    assert shutdown.is_set()


def test_schedule_installer_fails_without_helper_handshake(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"installer")
    expected = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    shutdown = threading.Event()
    bootstrap, bootstrap_sha256 = write_bootstrap_asset(tmp_path)

    class SlowHelper:
        def __init__(self):
            self.terminated = False
            self.waited = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == 5
            self.waited = True
            return 0

    helper = SlowHelper()
    monkeypatch.setattr(updater, "_launch_update_bootstrap", lambda **_kwargs: helper)
    monkeypatch.setattr(updater, "_wait_for_bootstrap_handshake", lambda *_args, **_kwargs: (_ for _ in ()).throw(updater.UpdateError("no handshake")))

    with pytest.raises(updater.UpdateError, match="no handshake"):
        updater.schedule_installer(
            installer,
            expected,
            tmp_path / "updater.log",
            shutdown.set,
            status_path=tmp_path / "update-status.json",
            target_version="1.2.1",
            bootstrap_path=bootstrap,
            bootstrap_sha256=bootstrap_sha256,
            bootstrap_protocol=1,
            bootstrap_version="1.0.0",
            delay_seconds=0,
        )
    assert not shutdown.is_set()
    assert helper.terminated
    assert helper.waited


def test_stop_update_helper_escalates_when_terminate_fails():
    class Helper:
        killed = False
        waited = False

        def poll(self):
            return None

        def terminate(self):
            raise OSError("terminate denied")

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            assert timeout == 5
            self.waited = True
            return 0

    helper = Helper()

    assert updater._stop_update_helper(helper) is None
    assert helper.killed
    assert helper.waited


def test_schedule_installer_preserves_handshake_error_when_helper_cannot_stop(tmp_path, monkeypatch):
    installer = tmp_path / "TikTokAffiliateReportSetup-v1.2.1.exe"
    installer.write_bytes(b"installer")
    expected = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    log_path = tmp_path / "updater.log"
    bootstrap, bootstrap_sha256 = write_bootstrap_asset(tmp_path)

    class StuckHelper:
        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("powershell.exe", timeout)

        def kill(self):
            return None

    monkeypatch.setattr(updater, "_launch_update_bootstrap", lambda **_kwargs: StuckHelper())
    monkeypatch.setattr(
        updater,
        "_wait_for_bootstrap_handshake",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(updater.UpdateError("no handshake")),
    )

    with pytest.raises(updater.UpdateError, match="no handshake") as caught:
        updater.schedule_installer(
            installer,
            expected,
            log_path,
            lambda: None,
            status_path=tmp_path / "update-status.json",
            target_version="1.2.1",
            bootstrap_path=bootstrap,
            bootstrap_sha256=bootstrap_sha256,
            bootstrap_protocol=1,
            bootstrap_version="1.0.0",
            delay_seconds=0,
        )

    assert any("không thoát sau khi terminate/kill" in note for note in caught.value.__notes__)
    assert "không thoát sau khi terminate/kill" in log_path.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_bootstrap_handshake_tolerates_real_slow_windows_powershell(tmp_path):
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    ack_path = tmp_path / "bootstrap-ack.json"
    probe = tmp_path / "slow-handshake.ps1"
    probe.write_text(
        r'''
param([string]$AckPath)
Start-Sleep -Seconds 8
$json = '{"schema":"tiktok-affiliate-report.update-bootstrap-ack.v1","phase":"ready","attempt_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","protocol":1,"bootstrap_version":"1.0.0","target_version":"2.0.7"}'
[System.IO.File]::WriteAllText($AckPath, $json, [System.Text.UTF8Encoding]::new($false))
''',
        encoding="utf-8-sig",
    )
    process = subprocess.Popen(
        [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe), str(ack_path)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    started = time.monotonic()
    try:
        updater._wait_for_bootstrap_handshake(
            ack_path,
            attempt_id="a" * 32,
            target_version="2.0.7",
            bootstrap_protocol=1,
            bootstrap_version="1.0.0",
            bootstrap_log=tmp_path / "bootstrap.log",
            timeout_seconds=15,
        )
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)

    elapsed = time.monotonic() - started
    assert 8 <= elapsed < 15


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_stop_update_helper_terminates_real_windows_powershell():
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    process = subprocess.Popen(
        [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "Start-Sleep -Seconds 60"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        assert updater._stop_update_helper(process) is None
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_bootstrap_handshake_tolerates_slow_powershell_cold_start(tmp_path, monkeypatch):
    clock = {"now": 0.0, "reads": 0}

    def monotonic():
        return clock["now"]

    def sleep(seconds):
        clock["now"] += seconds

    class DelayedAck:
        def read_text(self, **_kwargs):
            clock["reads"] += 1
            if clock["now"] < 8.0:
                raise FileNotFoundError
            return json.dumps(
                {
                    "schema": updater.BOOTSTRAP_ACK_SCHEMA,
                    "phase": "ready",
                    "attempt_id": "a" * 32,
                    "protocol": 1,
                    "bootstrap_version": "1.0.0",
                    "target_version": "2.0.7",
                }
            )

    def unused_read_status(_path):
        clock["reads"] += 1
        raise AssertionError("status handshake must not be used")

    monkeypatch.setattr(updater.time, "monotonic", monotonic)
    monkeypatch.setattr(updater.time, "sleep", sleep)
    monkeypatch.setattr(updater, "read_update_status", unused_read_status)

    updater._wait_for_bootstrap_handshake(
        DelayedAck(),
        attempt_id="a" * 32,
        target_version="2.0.7",
        bootstrap_protocol=1,
        bootstrap_version="1.0.0",
        bootstrap_log=tmp_path / "bootstrap.log",
    )

    assert clock["now"] >= 8.0
    assert clock["reads"] > 50


def test_bootstrap_handshake_checks_ready_ack_once_at_deadline(tmp_path, monkeypatch):
    clock = {"now": 0.0}

    monkeypatch.setattr(updater.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(updater.time, "sleep", lambda seconds: clock.update(now=clock["now"] + seconds))
    class DeadlineAck:
        def read_text(self, **_kwargs):
            if clock["now"] < 1.0:
                raise FileNotFoundError
            return json.dumps(
                {
                    "schema": updater.BOOTSTRAP_ACK_SCHEMA,
                    "phase": "ready",
                    "attempt_id": "a" * 32,
                    "protocol": 1,
                    "bootstrap_version": "1.0.0",
                    "target_version": "2.0.7",
                }
            )

    updater._wait_for_bootstrap_handshake(
        DeadlineAck(),
        attempt_id="a" * 32,
        target_version="2.0.7",
        bootstrap_protocol=1,
        bootstrap_version="1.0.0",
        bootstrap_log=tmp_path / "bootstrap.log",
        timeout_seconds=1.0,
    )

    assert clock["now"] == pytest.approx(1.0)


def test_bootstrap_handshake_rejects_stale_or_mismatched_ack(tmp_path):
    ack_path = tmp_path / "bootstrap-ack.json"
    ack_path.write_text(
        json.dumps(
            {
                "schema": updater.BOOTSTRAP_ACK_SCHEMA,
                "phase": "ready",
                "attempt_id": "b" * 32,
                "protocol": 1,
                "bootstrap_version": "1.0.0",
                "target_version": "2.0.7",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(updater.UpdateError, match="không xác nhận"):
        updater._wait_for_bootstrap_handshake(
            ack_path,
            attempt_id="a" * 32,
            target_version="2.0.7",
            bootstrap_protocol=1,
            bootstrap_version="1.0.0",
            bootstrap_log=tmp_path / "bootstrap.log",
            timeout_seconds=0,
        )

    ack = json.loads(ack_path.read_text(encoding="utf-8"))
    ack["attempt_id"] = "a" * 32
    ack["target_version"] = "2.0.8"
    ack_path.write_text(json.dumps(ack), encoding="utf-8")
    with pytest.raises(updater.UpdateError, match="handshake không hợp lệ"):
        updater._wait_for_bootstrap_handshake(
            ack_path,
            attempt_id="a" * 32,
            target_version="2.0.7",
            bootstrap_protocol=1,
            bootstrap_version="1.0.0",
            bootstrap_log=tmp_path / "bootstrap.log",
            timeout_seconds=0,
        )


def test_version_validation():
    with pytest.raises(updater.UpdateError, match="Phiên bản"):
        updater._parse_version("1.2")


def test_status_write_survives_a_concurrent_reader_holding_the_file(tmp_path):
    """Giao diện hỏi /progress mỗi 750 ms trong lúc cài, mà endpoint đó đọc đúng file này.

    Trên Windows os.replace ném PermissionError nếu file đích đang mở, kể cả chỉ mở để đọc.
    Đo trên gate cập nhật thật: 2 trong 5 lần cài hỏng ngay ở lần ghi trạng thái đầu tiên với
    lỗi "Không thể ghi trạng thái cập nhật." và cả bản cập nhật bị bỏ dở.
    """
    status_path = tmp_path / "update-status.json"
    updater.write_update_status(status_path, phase="downloading", target_version="9.9.9")

    released = threading.Event()
    opened = threading.Event()

    def hold_open() -> None:
        with status_path.open("r", encoding="utf-8") as handle:
            handle.read()
            opened.set()
            released.wait(2)

    reader = threading.Thread(target=hold_open, daemon=True)
    reader.start()
    assert opened.wait(2)
    timer = threading.Timer(0.2, released.set)
    timer.start()
    try:
        updater.write_update_status(status_path, phase="installing", target_version="9.9.9")
    finally:
        released.set()
        timer.cancel()
        reader.join(2)

    assert json.loads(status_path.read_text(encoding="utf-8"))["phase"] == "installing"


def test_status_write_still_reports_failure_when_the_file_never_frees_up(tmp_path, monkeypatch):
    """Thử lại là để vượt qua va chạm khoảnh khắc, không phải để nuốt lỗi thật."""
    status_path = tmp_path / "update-status.json"

    def always_denied(source, destination):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(updater.os, "replace", always_denied)
    # Rút cửa sổ thử lại để test không phải chờ hết 2 giây thật.
    monkeypatch.setattr(updater, "_replace_with_retry", functools.partial(updater._replace_with_retry, timeout=0.05))
    with pytest.raises(updater.UpdateError, match="Không thể ghi trạng thái cập nhật."):
        updater.write_update_status(status_path, phase="downloading", target_version="9.9.9")


def test_download_retries_a_transient_network_drop_then_succeeds(tmp_path, monkeypatch):
    """Gói cài ~46 MB; một cú rớt mạng không đáng làm hỏng cả bản cập nhật.

    Đo trên gate cập nhật thật: có máy báo "Không thể tải gói cập nhật từ nguồn phát hành"
    trong khi các máy khác cùng lúc tải xong bình thường, và GitHub trả 503 cho vài máy khi
    năm máy song song cùng kéo một tệp.
    """
    payload = b"x" * 4096
    attempts = []

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def flaky_urlopen(request, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise URLError("connection reset")
        return _Response(payload)

    monkeypatch.setattr(updater, "urlopen", flaky_urlopen)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)
    destination = tmp_path / "asset.bin"

    digest = updater._download_file("https://example.test/a.bin", destination, len(payload), 1 << 20)

    assert len(attempts) == 3
    assert destination.read_bytes() == payload
    assert digest == hashlib.sha256(payload).hexdigest().upper()
    assert not list(tmp_path.glob("*.download"))


def test_download_gives_up_after_the_retry_budget(tmp_path, monkeypatch):
    """Thử lại là để vượt sự cố thoáng qua, không phải để treo mãi hay nuốt lỗi thật."""
    attempts = []

    def always_down(request, timeout=None):
        attempts.append(1)
        raise URLError("connection reset")

    monkeypatch.setattr(updater, "urlopen", always_down)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)

    with pytest.raises(updater.UpdateError, match="Không thể tải update asset."):
        updater._download_file("https://example.test/a.bin", tmp_path / "asset.bin", 10, 1 << 20)

    assert len(attempts) == updater._DOWNLOAD_ATTEMPTS
    assert not list(tmp_path.glob("*"))
