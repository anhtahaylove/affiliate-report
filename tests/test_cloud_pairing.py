from __future__ import annotations

import hashlib
from collections.abc import Callable

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from affiliate_report.cloud_pairing import (
    CloudPairingError,
    CloudPairingRunner,
    decrypt_envelope,
    encrypt_envelope,
    relay_urls,
)


class RelayHarness:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.encrypted = b""
        self.claim_header = ""
        self.ack_count = 0
        self.cancel_count = 0
        self.fail_status_once = False

    def factory(self, base_url: str) -> httpx.Client:
        return httpx.Client(base_url=base_url, transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/api/v1/sessions":
            self.created = request.read() and __import__("json").loads(request.content)
            session_id = str(self.created["session_id"])
            return httpx.Response(
                201,
                json={
                    "schema": 1,
                    "session_id": session_id,
                    "state": "created",
                    "upload_url": f"{request.url.scheme}://{request.url.host}/pair/{session_id}",
                },
            )
        if request.method == "GET" and path.endswith("/file"):
            self.claim_header = request.headers.get("authorization", "")
            return httpx.Response(
                200,
                content=self.encrypted,
                headers={"content-length": str(len(self.encrypted)), "content-type": "application/octet-stream"},
            )
        if request.method == "POST" and path.endswith("/ack"):
            self.claim_header = request.headers.get("authorization", "")
            self.ack_count += 1
            return httpx.Response(200, json={"schema": 1, "state": "deleted"})
        if request.method == "DELETE" and path.startswith("/api/v1/sessions/"):
            self.claim_header = request.headers.get("authorization", "")
            self.cancel_count += 1
            return httpx.Response(200, json={"schema": 1, "state": "deleted"})
        if request.method == "GET" and path.startswith("/api/v1/sessions/"):
            self.claim_header = request.headers.get("authorization", "")
            if self.fail_status_once:
                self.fail_status_once = False
                return httpx.Response(503, json={"error": {"detail": "Tạm thời gián đoạn"}})
            state = "ready" if self.encrypted else "created"
            return httpx.Response(200, json={"schema": 1, "session_id": path.rsplit("/", 1)[-1], "state": state})
        return httpx.Response(404)


def test_envelope_round_trip_and_aad_tamper_rejection() -> None:
    key = bytes(range(32))
    encrypted = encrypt_envelope(session_id="session-a", aes_key=key, filename="đơn TikTok.xlsx", data=b"xlsx")

    assert decrypt_envelope(session_id="session-a", aes_key=key, encrypted=encrypted, max_upload_mb=20) == (
        "đơn TikTok.xlsx",
        b"xlsx",
    )
    with pytest.raises(CloudPairingError, match="Không xác minh"):
        decrypt_envelope(session_id="session-b", aes_key=key, encrypted=encrypted, max_upload_mb=20)

    tampered = bytearray(encrypted)
    tampered[-1] ^= 1
    with pytest.raises(CloudPairingError, match="Không xác minh"):
        decrypt_envelope(session_id="session-a", aes_key=key, encrypted=bytes(tampered), max_upload_mb=20)


def test_envelope_rejects_non_xlsx_and_size_mismatch() -> None:
    with pytest.raises(CloudPairingError, match="Chỉ nhận file .xlsx"):
        encrypt_envelope(session_id="session", aes_key=b"k" * 32, filename="photo.jpg", data=b"x")

    key = b"k" * 32
    metadata = b'{"schema":1,"filename":"orders.xlsx","size":999}'
    plain = len(metadata).to_bytes(4, "big") + metadata + b"actual"
    iv = b"i" * 12
    encrypted = iv + AESGCM(key).encrypt(iv, plain, b"affiliate-report-pairing-v1:session")
    with pytest.raises(CloudPairingError, match="Dung lượng file không khớp"):
        decrypt_envelope(session_id="session", aes_key=key, encrypted=encrypted, max_upload_mb=20)


def test_runner_uses_only_hashes_at_relay_and_imports_exact_plaintext() -> None:
    relay = RelayHarness()
    imported: list[tuple[str, str, bytes]] = []
    runner = CloudPairingRunner(
        nhan_tep=lambda account, filename, data: imported.append((account, filename, data)) or {"inserted": 3},
        max_upload_mb=20,
        endpoints=("https://relay.example",),
        client_factory=relay.factory,
        start_thread=False,
    )

    session = runner.bat("SHOP_A")
    assert relay.created is not None
    assert relay.created["upload_token_hash"] == hashlib.sha256(session.upload_token.encode()).hexdigest()
    assert relay.created["claim_token_hash"] == hashlib.sha256(session.claim_token.encode()).hexdigest()
    serialized = str(relay.created)
    assert session.upload_token not in serialized
    assert session.claim_token not in serialized
    assert session.aes_key.hex() not in serialized
    public = runner.trang_thai()
    assert set(public).isdisjoint({"url", "upload_url", "upload_token", "claim_token", "aes_key"})
    assert public["relay_host"] == "relay.example"

    relay.encrypted = encrypt_envelope(
        session_id=session.session_id,
        aes_key=session.aes_key,
        filename="affiliate.xlsx",
        data=b"real xlsx bytes",
    )
    assert runner.poll_once() is True
    assert imported == [("SHOP_A", "affiliate.xlsx", b"real xlsx bytes")]
    assert relay.ack_count == 1
    assert relay.claim_header == f"Pairing {session.claim_token}"
    assert runner.trang_thai() == {
        "enabled": False,
        "mode": "cloud",
        "so_lan_nhan": 1,
        "phase": "idle",
        "message": "Đã nhận và nhập file từ điện thoại.",
        "error": "",
        "result": {"inserted": 3},
    }


def test_runner_retries_transient_status_and_cancel_deletes_remote() -> None:
    relay = RelayHarness()
    relay.fail_status_once = True
    runner = CloudPairingRunner(
        nhan_tep=lambda *_: {},
        max_upload_mb=20,
        endpoints=("https://relay.example",),
        client_factory=relay.factory,
        start_thread=False,
    )
    runner.bat("SHOP_A")

    assert runner.poll_once() is False
    assert "tự thử lại" in runner.trang_thai()["message"]
    runner.tat()
    assert relay.cancel_count == 1
    assert runner.trang_thai()["enabled"] is False


def test_runner_falls_back_to_second_relay() -> None:
    relay = RelayHarness()

    def factory(base_url: str) -> httpx.Client:
        if base_url == "https://primary.example":
            def unavailable(_: httpx.Request) -> httpx.Response:
                return httpx.Response(503, json={"error": {"detail": "unavailable"}})

            return httpx.Client(base_url=base_url, transport=httpx.MockTransport(unavailable))
        return relay.factory(base_url)

    runner = CloudPairingRunner(
        nhan_tep=lambda *_: {},
        max_upload_mb=20,
        endpoints=("https://primary.example", "https://fallback.workers.dev"),
        client_factory=factory,
        start_thread=False,
    )
    session = runner.bat("SHOP_A")
    assert session.relay_url == "https://fallback.workers.dev"
    runner.tat()


def test_runner_rejects_upload_url_on_lookalike_origin() -> None:
    relay = RelayHarness()

    def malicious(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/sessions":
            payload = __import__("json").loads(request.content)
            return httpx.Response(
                201,
                json={
                    "schema": 1,
                    "session_id": payload["session_id"],
                    "state": "created",
                    "upload_url": f"https://relay.example.evil/pair/{payload['session_id']}",
                },
            )
        return relay.handle(request)

    runner = CloudPairingRunner(
        nhan_tep=lambda *_: {},
        max_upload_mb=20,
        endpoints=("https://relay.example",),
        client_factory=lambda base_url: httpx.Client(base_url=base_url, transport=httpx.MockTransport(malicious)),
        start_thread=False,
    )

    with pytest.raises(CloudPairingError, match="địa chỉ upload không hợp lệ"):
        runner.bat("SHOP_A")


def test_runner_surfaces_safe_import_error_and_deletes_ciphertext() -> None:
    relay = RelayHarness()
    runner = CloudPairingRunner(
        nhan_tep=lambda *_: (_ for _ in ()).throw(RuntimeError("C:\\Users\\secret\\data.xlsx")),
        max_upload_mb=20,
        endpoints=("https://relay.example",),
        client_factory=relay.factory,
        start_thread=False,
    )
    session = runner.bat("SHOP_A")
    relay.encrypted = encrypt_envelope(
        session_id=session.session_id,
        aes_key=session.aes_key,
        filename="orders.xlsx",
        data=b"xlsx",
    )

    assert runner.poll_once() is True
    status = runner.trang_thai()
    assert relay.ack_count == 1
    assert status["error"] == "Không nhập được file Excel. Hãy kiểm tra đúng file xuất từ TikTok rồi thử lại."
    assert "Users" not in str(status)


def test_relay_urls_require_https_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AFFILIATE_REPORT_PAIRING_RELAY_URL", "http://relay.example/path")
    with pytest.raises(CloudPairingError, match="HTTPS"):
        relay_urls()


@pytest.mark.parametrize("factory_error", [httpx.ConnectError("offline"), ValueError("bad JSON")])
def test_create_failure_does_not_leak_exception_details(factory_error: Exception) -> None:
    def factory(_: str) -> httpx.Client:
        def fail(request: httpx.Request) -> httpx.Response:
            raise factory_error

        return httpx.Client(base_url="https://relay.example", transport=httpx.MockTransport(fail))

    runner = CloudPairingRunner(
        nhan_tep=lambda *_: {}, max_upload_mb=20, endpoints=("https://relay.example",), client_factory=factory, start_thread=False
    )
    with pytest.raises(CloudPairingError) as caught:
        runner.bat("SHOP_A")
    assert "offline" not in str(caught.value)
    assert "bad JSON" not in str(caught.value)
