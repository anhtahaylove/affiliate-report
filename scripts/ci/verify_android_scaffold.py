from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def require_valid_android_resources() -> None:
    resource_root = ROOT / "android/native/app/src/main/res"
    for resource in sorted(resource_root.rglob("*.xml")):
        try:
            ET.parse(resource)
        except ET.ParseError as exc:
            relative = resource.relative_to(ROOT)
            raise SystemExit(f"{relative}: invalid Android resource XML: {exc}") from exc


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"{path}: missing contract(s): {missing}")


require(
    "android/native/app/build.gradle",
    'applicationId "vn.io.huuhungn.affiliatereport"',
    "minSdkVersion rootProject.ext.minSdkVersion",
    'versionCode 2001002',
    'versionName "2.1.2"',
    "version = '3.12'",
    "abiFilters 'arm64-v8a'",
    "abiFilters 'x86_64'",
    "Release signing is fail-closed",
    "storeType 'PKCS12'",
)
require(
    "android/native/variables.gradle",
    "minSdkVersion = 24",
    "compileSdkVersion = 36",
    "targetSdkVersion = 36",
)
require(
    "android/native/app/src/main/AndroidManifest.xml",
    'android:name=".AffiliateReportApplication"',
    'android:allowBackup="false"',
    'android:networkSecurityConfig="@xml/network_security_config"',
    "android.permission.REQUEST_INSTALL_PACKAGES",
    "androidx.core.content.FileProvider",
)
require(
    "android/native/app/src/main/res/xml/file_paths.xml",
    '<cache-path name="verified_updates" path="updates/"',
)
require(
    "android/native/app/src/main/java/vn/io/huuhungn/affiliatereport/MainActivity.java",
    "ACTION_CREATE_DOCUMENT",
    "ACTION_MANAGE_UNKNOWN_APP_SOURCES",
    "FLAG_GRANT_READ_URI_PERMISSION",
    "isTrustedLoopbackUrl(source)",
    'addJavascriptInterface(',
    '"AffiliateReportAndroid"',
)
require_valid_android_resources()
native_bootstrap = (ROOT / "android/native/app/src/main/assets/public/index.html").read_text(encoding="utf-8")
for forbidden in ("fetch(`${appUrl}health`", "location.replace(appUrl)"):
    if forbidden in native_bootstrap:
        raise SystemExit(f"Generated Android bootstrap still contains unsafe self-navigation: {forbidden}")
if native_bootstrap != (ROOT / "android/web-bootstrap/index.html").read_text(encoding="utf-8"):
    raise SystemExit("Generated Android bootstrap is stale; run pnpm --dir android sync")
require(
    "android/native/app/src/main/python/android_runtime.py",
    '"APP_PLATFORM": "android"',
    '"AUTH_MODE": "local"',
    '"127.0.0.1"',
    '"DATABASE_URL"',
    '"WEB_STATIC_DIR"',
)
requirements = (ROOT / "requirements-android.txt").read_text(encoding="utf-8")
for forbidden in ("pystray", "psycopg", "authlib", "uvicorn[standard]"):
    if re.search(rf"(?im)^\s*{re.escape(forbidden)}", requirements):
        raise SystemExit(f"requirements-android.txt must not include desktop-only dependency {forbidden}")
for required in ("pandas==2.1.3", "cryptography==42.0.8", "pydantic==1.10.24"):
    if required not in requirements:
        raise SystemExit(f"requirements-android.txt missing Android-compatible pin {required}")

print("Android scaffold contracts: OK")
