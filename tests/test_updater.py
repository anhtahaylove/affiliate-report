from __future__ import annotations

import base64
import hashlib
import io
import json
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tiktok_affiliate_report.updater as updater

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
    version: str = "1.2.0",
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


def test_check_and_download_update_with_verified_signed_public_feed(tmp_path, monkeypatch):
    manifest, signature, installer = stable_feed()
    seen_headers = install_feed(monkeypatch, manifest, signature, installer)

    checked = updater.check_for_update(current_version="1.1.1", token="ignored")
    downloaded = updater.download_latest_update(tmp_path, current_version="1.1.1", token="ignored")

    assert set(json.loads(manifest)) == {"schema", "app_id", "channel", "version", "published_at", "release_url", "installer"}
    assert checked["available"] is True
    assert checked["installable"] is True
    assert checked["source_repo"] == "anhtahaylove/tiktok-affiliate-report-updates"
    assert downloaded["sha256"] == hashlib.sha256(installer).hexdigest().upper()
    assert Path(downloaded["installer_path"]).read_bytes() == installer
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
            "name": "TikTokAffiliateReportSetup-v1.2.0.exe",
            "url": "https://example.test/TikTokAffiliateReportSetup-v1.2.0.exe",
            "size": 0,
            "sha256": "0" * 64,
        }
    )
    install_feed(monkeypatch, manifest, signature, installer)
    with pytest.raises(updater.UpdateError, match="Kích thước"):
        updater.check_for_update(current_version="1.1.1")

    manifest, signature, installer = stable_feed(
        installer_info={
            "name": "TikTokAffiliateReportSetup-v1.2.0.exe",
            "url": "https://example.test/TikTokAffiliateReportSetup-v1.2.0.exe",
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


def test_version_validation():
    with pytest.raises(updater.UpdateError, match="Phiên bản"):
        updater._parse_version("1.2")
