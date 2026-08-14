from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from affiliate_report.updater import (
    UPDATE_APP_ID,
    UPDATE_BOOTSTRAP_NAME,
    UPDATE_BOOTSTRAP_PROTOCOL,
    UPDATE_BOOTSTRAP_VERSION,
    UPDATE_CHANNEL,
    UPDATE_SCHEMA,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create signed public update feed files.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--bootstrap", required=True, type=Path)
    parser.add_argument("--asset-url", required=True)
    parser.add_argument("--bootstrap-url", required=True)
    parser.add_argument("--android-apk", type=Path)
    parser.add_argument("--android-url", default="")
    parser.add_argument("--android-min-sdk", type=int, default=24)
    parser.add_argument("--android-abi", action="append", dest="android_abis", default=[])
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--output-dir", default="artifacts/installer", type=Path)
    parser.add_argument("--published-at", default="")
    parser.add_argument("--private-key-b64", default=os.getenv("UPDATE_SIGNING_KEY_B64", ""))
    parser.add_argument("--print-public-key", action="store_true")
    args = parser.parse_args()

    private_key = _private_key(args.private_key_b64)
    if args.print_public_key:
        public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        print(base64.b64encode(public).decode("ascii"))

    installer = args.installer.resolve()
    if not installer.is_file():
        raise SystemExit(f"Missing installer: {installer}")
    # Chấp nhận cả hai đời tên: bản v2.0.25 trên máy người dùng chỉ nhận tên cũ, nên gói phát
    # hành phải giữ tên cũ cho tới khi mọi máy lên >= v2.0.27. Xem ghi chú trong AffiliateReport.iss.
    ten_hop_le = (f"AffiliateReportSetup-v{args.version}.exe", f"TikTokAffiliateReportSetup-v{args.version}.exe")
    if installer.name not in ten_hop_le:
        raise SystemExit(f"Installer must be named one of: {', '.join(ten_hop_le)}")

    digest = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    bootstrap = args.bootstrap.resolve()
    if not bootstrap.is_file():
        raise SystemExit(f"Missing updater bootstrap: {bootstrap}")
    if bootstrap.name != UPDATE_BOOTSTRAP_NAME:
        raise SystemExit(f"Updater bootstrap must be named {UPDATE_BOOTSTRAP_NAME}")
    bootstrap_digest = hashlib.sha256(bootstrap.read_bytes()).hexdigest().upper()
    manifest = {
        "schema": UPDATE_SCHEMA,
        "app_id": UPDATE_APP_ID,
        "channel": UPDATE_CHANNEL,
        "version": args.version,
        "published_at": args.published_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "release_url": args.release_url,
        "installer": {
            "name": installer.name,
            "url": args.asset_url,
            "size": installer.stat().st_size,
            "sha256": digest,
        },
        "bootstrap": {
            "protocol": UPDATE_BOOTSTRAP_PROTOCOL,
            "version": UPDATE_BOOTSTRAP_VERSION,
            "name": bootstrap.name,
            "url": args.bootstrap_url,
            "size": bootstrap.stat().st_size,
            "sha256": bootstrap_digest,
        },
    }
    if args.android_apk:
        android_apk = args.android_apk.resolve()
        if not android_apk.is_file():
            raise SystemExit(f"Missing Android APK: {android_apk}")
        expected_android_name = f"AffiliateReport-v{args.version}-arm64.apk"
        if android_apk.name != expected_android_name:
            raise SystemExit(f"Android APK must be named {expected_android_name}")
        if not args.android_url.startswith("https://"):
            raise SystemExit("Android APK URL must use HTTPS")
        if args.android_min_sdk < 24:
            raise SystemExit("Android min SDK must be at least 24")
        android_abis = args.android_abis or ["arm64-v8a"]
        if android_abis != ["arm64-v8a"]:
            raise SystemExit("Stable Android release must contain only the arm64-v8a ABI")
        manifest["android"] = {
            "name": android_apk.name,
            "url": args.android_url,
            "size": android_apk.stat().st_size,
            "sha256": hashlib.sha256(android_apk.read_bytes()).hexdigest().upper(),
            "version": args.version,
            "min_sdk": args.android_min_sdk,
            "abis": android_abis,
        }
    payload = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    signature = {
        "key_id": args.key_id,
        "signature": base64.b64encode(private_key.sign(payload)).decode("ascii"),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "stable.json").write_bytes(payload)
    signature_payload = (json.dumps(signature, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    (args.output_dir / "stable.json.sig").write_bytes(signature_payload)
    print(f"Wrote {args.output_dir / 'stable.json'} and stable.json.sig")
    return 0


def _private_key(value: str) -> Ed25519PrivateKey:
    if not value:
        raise SystemExit("UPDATE_SIGNING_KEY_B64 is required")
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) != 32:
            raise ValueError("Ed25519 private key must be 32 raw bytes")
        return Ed25519PrivateKey.from_private_bytes(raw)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
