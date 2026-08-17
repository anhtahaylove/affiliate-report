from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx


PASSPHRASE = "Android-Smoke-2026!"
ACCOUNT = "ANDROIDSMOKE"
ROUTES = (
    "/",
    "/analytics/",
    "/orders/",
    "/imports/",
    "/targets/",
    "/accounts/",
    "/settings/preferences/",
    "/settings/data/",
    "/settings/sync/",
    "/settings/update/",
    "/settings/users/",
)


def _wait(client: httpx.Client, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    error = "not started"
    while time.monotonic() < deadline:
        try:
            response = client.get("/health", timeout=3)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - preserve last runtime failure in CI
            error = str(exc)
            time.sleep(1)
    raise RuntimeError(f"Android loopback runtime did not become healthy: {error}")


def _assert_routes(client: httpx.Client) -> None:
    for route in ROUTES:
        response = client.get(route)
        if response.status_code != 200 or "<!DOCTYPE html" not in response.text[:200]:
            raise RuntimeError(f"Static route {route} failed: HTTP {response.status_code}")


def _seed(client: httpx.Client, fixture: Path, package: Path) -> dict:
    health = _wait(client)
    if health.get("app_version") != "2.2.0":
        raise RuntimeError(f"Unexpected Android runtime version: {health!r}")
    _assert_routes(client)
    account = client.post(
        "/api/v1/accounts",
        json={"code": ACCOUNT, "display_name": "Android Smoke", "display_order": 10},
    )
    if account.status_code not in {201, 409}:
        raise RuntimeError(f"Could not seed Android account: {account.status_code} {account.text}")
    with fixture.open("rb") as stream:
        imported = client.post(
            "/api/v1/imports",
            data={"account": ACCOUNT},
            files={"file": (fixture.name, stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=120,
        )
    imported.raise_for_status()
    result = imported.json()
    if result.get("inserted", 0) + result.get("updated", 0) + result.get("unchanged", 0) < 1:
        raise RuntimeError(f"Real Excel fixture produced no accepted rows: {result!r}")
    exported = client.post("/api/v1/sync/export", json={"passphrase": PASSPHRASE}, timeout=120)
    exported.raise_for_status()
    if not exported.content.startswith(b"AFFSYNC1"):
        raise RuntimeError("Android sync export did not produce AFFSYNC1")
    package.write_bytes(exported.content)
    return {"health": health, "import": result, "package_bytes": package.stat().st_size}


def _verify_persistence(client: httpx.Client, expected_version: str) -> dict:
    health = _wait(client)
    if health.get("app_version") != expected_version:
        raise RuntimeError(f"Android runtime did not upgrade to {expected_version}: {health!r}")
    meta = client.get("/api/v1/meta").json()
    history = client.get("/api/v1/imports", params={"account": ACCOUNT, "limit": 10}).json()
    if ACCOUNT not in meta.get("accounts", []) or history.get("count", 0) < 1:
        raise RuntimeError("Android process restart did not preserve the seeded database")
    return {"health": health, "imports": history["count"]}


def _restore(client: httpx.Client, package: Path) -> dict:
    health = _wait(client)
    with package.open("rb") as stream:
        preview_response = client.post(
            "/api/v1/sync/preview",
            data={"passphrase": PASSPHRASE},
            files={"package": (package.name, stream, "application/vnd.affiliate-report.sync")},
            timeout=120,
        )
    preview_response.raise_for_status()
    preview = preview_response.json()
    resolutions = {item["key"]: "incoming" for item in preview.get("conflicts", [])}
    imported = client.post(
        "/api/v1/sync/import",
        json={
            "preview_id": preview["preview_id"],
            "confirmation": "DONG BO",
            "conflict_resolutions": resolutions,
        },
        timeout=120,
    )
    imported.raise_for_status()
    meta = client.get("/api/v1/meta").json()
    history = client.get("/api/v1/imports", params={"account": ACCOUNT, "limit": 10}).json()
    if ACCOUNT not in meta.get("accounts", []) or history.get("count", 0) < 1:
        raise RuntimeError("AFFSYNC1 restore did not recreate the imported Android data")
    return {"health": health, "preview": preview["preview_id"], "result": imported.json(), "imports": history["count"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("seed", "persist", "restore"), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:9876")
    parser.add_argument("--fixture", type=Path, default=Path("tests/fixtures/affiliate_orders_e2e-sample.xlsx"))
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--expected-version", default="2.2.0")
    parser.add_argument("--android-token", default=os.getenv("ANDROID_LOCAL_TOKEN", ""))
    args = parser.parse_args()
    if len(args.android_token) < 32:
        raise RuntimeError("Private Android local token is required for runtime smoke")
    with httpx.Client(
        base_url=args.base_url,
        headers={"X-Android-Local-Token": args.android_token},
        follow_redirects=True,
        timeout=30,
    ) as client:
        if args.phase == "seed":
            result = _seed(client, args.fixture, args.package)
        elif args.phase == "persist":
            result = _verify_persistence(client, args.expected_version)
        else:
            result = _restore(client, args.package)
    print(json.dumps({"phase": args.phase, **result}, sort_keys=True))


if __name__ == "__main__":
    main()
