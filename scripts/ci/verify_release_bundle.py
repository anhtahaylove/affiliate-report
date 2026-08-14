from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from affiliate_report import updater


BOOTSTRAP_NAME = "TikTokAffiliateUpdater-v1.0.0.ps1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def verify_bundle(directory: Path, manifest_directory: Path, version: str, repository: str) -> None:
    tag = f"v{version}"
    installer_name = f"AffiliateReportSetup-v{version}.exe"
    apk_name = f"AffiliateReport-v{version}-arm64.apk"
    expected_files = {
        installer_name,
        apk_name,
        BOOTSTRAP_NAME,
        "SHA256SUMS.txt",
        "stable.json",
        "stable.json.sig",
    }
    actual_files = {item.name for item in directory.iterdir() if item.is_file()}
    if actual_files != expected_files:
        raise SystemExit(
            f"Release must contain exactly six verified assets; expected={sorted(expected_files)!r}, "
            f"actual={sorted(actual_files)!r}"
        )

    downloadable = {installer_name, apk_name, BOOTSTRAP_NAME}
    checksum_lines = [line for line in (directory / "SHA256SUMS.txt").read_text("utf-8").splitlines() if line]
    if len(checksum_lines) != len(downloadable):
        raise SystemExit("SHA256SUMS must contain exactly installer, Android APK and updater bootstrap")
    entries: dict[str, str] = {}
    for line in checksum_lines:
        match = re.fullmatch(r"([A-Fa-f0-9]{64})  ([A-Za-z0-9._-]+)", line)
        if not match or match.group(2) in entries:
            raise SystemExit("SHA256SUMS contains a malformed, duplicate or unexpected entry")
        entries[match.group(2)] = match.group(1).upper()
    if set(entries) != downloadable:
        raise SystemExit("SHA256SUMS must contain exactly installer, Android APK and updater bootstrap")
    for name, expected_hash in entries.items():
        if _sha256(directory / name) != expected_hash:
            raise SystemExit(f"Checksum mismatch for {name}")

    manifest = updater.verify_update_manifest_bytes(
        (manifest_directory / "stable.json").read_bytes(),
        (manifest_directory / "stable.json.sig").read_bytes(),
    )
    release_url = f"https://github.com/{repository}/releases/tag/{tag}"
    asset_base = f"https://github.com/{repository}/releases/download/{tag}"
    if manifest["version"] != version or manifest["release_url"] != release_url:
        raise SystemExit("Signed manifest release identity is invalid")

    expected_manifest_assets = {
        "installer": (installer_name, f"{asset_base}/{installer_name}"),
        "bootstrap": (BOOTSTRAP_NAME, f"{asset_base}/{BOOTSTRAP_NAME}"),
        "android": (apk_name, f"{asset_base}/{apk_name}"),
    }
    for key, (name, url) in expected_manifest_assets.items():
        metadata = manifest.get(key)
        path = directory / name
        if not isinstance(metadata, dict):
            raise SystemExit(f"Signed manifest is missing {key}")
        if metadata.get("name") != name or metadata.get("url") != url:
            raise SystemExit(f"Signed manifest {key} identity is invalid")
        if metadata.get("size") != path.stat().st_size or metadata.get("sha256") != _sha256(path):
            raise SystemExit(f"Signed manifest {key} integrity metadata is invalid")

    android = manifest["android"]
    if (
        android.get("version") != version
        or android.get("min_sdk") != 24
        or android.get("abis") != ["arm64-v8a"]
    ):
        raise SystemExit("Signed Android compatibility metadata is invalid")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the exact Affiliate Report release bundle")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--manifest-directory", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    verify_bundle(
        args.directory.resolve(),
        (args.manifest_directory or args.directory).resolve(),
        args.version,
        args.repository,
    )


if __name__ == "__main__":
    main()
