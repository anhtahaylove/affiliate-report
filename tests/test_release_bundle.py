from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.ci import verify_release_bundle


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict]:
    version = "2.1.0"
    repo = "anhtahaylove/affiliate-report"
    names = {
        "installer": f"AffiliateReportSetup-v{version}.exe",
        "android": f"AffiliateReport-v{version}-arm64.apk",
        "bootstrap": verify_release_bundle.BOOTSTRAP_NAME,
    }
    for key, name in names.items():
        (tmp_path / name).write_bytes(f"{key}-bytes".encode())
    (tmp_path / "stable.json").write_bytes(b"manifest")
    (tmp_path / "stable.json.sig").write_bytes(b"signature")
    (tmp_path / "SHA256SUMS.txt").write_text(
        "".join(f"{_sha(tmp_path / name).lower()}  {name}\n" for name in names.values()),
        encoding="utf-8",
    )
    tag = f"v{version}"
    base = f"https://github.com/{repo}/releases/download/{tag}"
    manifest = {
        "version": version,
        "release_url": f"https://github.com/{repo}/releases/tag/{tag}",
    }
    for key, name in names.items():
        path = tmp_path / name
        manifest[key] = {
            "name": name,
            "url": f"{base}/{name}",
            "size": path.stat().st_size,
            "sha256": _sha(path),
        }
    manifest["android"].update(version=version, min_sdk=24, abis=["arm64-v8a"])
    monkeypatch.setattr(verify_release_bundle, "_verify_update_manifest_bytes", lambda *_: manifest)
    return tmp_path, manifest


def test_verify_release_bundle_accepts_exact_six_asset_contract(tmp_path, monkeypatch):
    directory, _manifest = _bundle(tmp_path, monkeypatch)
    verify_release_bundle.verify_bundle(directory, directory, "2.1.0", "anhtahaylove/affiliate-report")


def test_verify_release_bundle_rejects_extra_checksum_entry(tmp_path, monkeypatch):
    directory, _manifest = _bundle(tmp_path, monkeypatch)
    with (directory / "SHA256SUMS.txt").open("a", encoding="utf-8") as stream:
        stream.write(f"{'0' * 64}  unexpected.bin\n")
    with pytest.raises(SystemExit, match="exactly installer, Android APK"):
        verify_release_bundle.verify_bundle(directory, directory, "2.1.0", "anhtahaylove/affiliate-report")


def test_verify_release_bundle_rejects_android_compatibility_drift(tmp_path, monkeypatch):
    directory, manifest = _bundle(tmp_path, monkeypatch)
    manifest["android"]["min_sdk"] = 26
    with pytest.raises(SystemExit, match="Android compatibility"):
        verify_release_bundle.verify_bundle(directory, directory, "2.1.0", "anhtahaylove/affiliate-report")
