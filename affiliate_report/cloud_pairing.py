"""Cloud Pairing client for the desktop application.

Cloudflare only receives short-lived ciphertext.  The AES key and claim capability live in
memory in this process; the upload capability is embedded in the QR URL fragment, which is not
sent by browsers when they request the upload page.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlparse

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .pairing import TOKEN_TTL_SECONDS, ma_qr_svg
from .version import APP_VERSION

PROTOCOL_SCHEMA = 1
HARD_TTL_SECONDS = 900
TOKEN_BYTES = 32
KEY_BYTES = 32
IV_BYTES = 12
ENVELOPE_METADATA_LIMIT = 4096
DEFAULT_RELAY_URL = "https://aff-report.huuhungn.io.vn"
DEFAULT_RELAY_FALLBACK_URL = "https://affiliate-report-pairing-relay.huuhungn.workers.dev"
RELAY_URL_ENV = "AFFILIATE_REPORT_PAIRING_RELAY_URL"
RELAY_FALLBACK_ENV = "AFFILIATE_REPORT_PAIRING_RELAY_FALLBACK_URL"


class CloudPairingError(Exception):
    """A safe, user-facing cloud-pairing failure."""


@dataclass
class CloudPairingSession:
    session_id: str
    account: str
    relay_url: str
    upload_url: str
    upload_token: str
    claim_token: str
    aes_key: bytes
    expires_at: float
    qr_svg: str
    phase: str = "created"


def relay_urls() -> tuple[str, ...]:
    """Configured relay endpoints, custom domain first and workers.dev as optional fallback."""

    configured = os.environ.get(RELAY_URL_ENV, DEFAULT_RELAY_URL)
    fallback = os.environ.get(RELAY_FALLBACK_ENV, DEFAULT_RELAY_FALLBACK_URL)
    result: list[str] = []
    for raw in (configured, fallback):
        value = raw.strip().rstrip("/")
        if value and value not in result:
            _validate_relay_url(value)
            result.append(value)
    return tuple(result)


def encrypt_envelope(*, session_id: str, aes_key: bytes, filename: str, data: bytes) -> bytes:
    """Reference encoder used by tests; the phone page implements the same protocol in WebCrypto."""

    safe_name = _safe_xlsx_name(filename)
    metadata = json.dumps(
        {
            "schema": PROTOCOL_SCHEMA,
            "filename": safe_name,
            "size": len(data),
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(metadata) > ENVELOPE_METADATA_LIMIT:
        raise CloudPairingError("Tên file quá dài.")
    plain = len(metadata).to_bytes(4, "big") + metadata + data
    iv = secrets.token_bytes(IV_BYTES)
    aad = f"affiliate-report-pairing-v1:{session_id}".encode()
    return iv + AESGCM(aes_key).encrypt(iv, plain, aad)


def decrypt_envelope(
    *, session_id: str, aes_key: bytes, encrypted: bytes, max_upload_mb: int
) -> tuple[str, bytes]:
    """Authenticate and decode a cloud upload without writing plaintext to disk."""

    if len(aes_key) != KEY_BYTES or len(encrypted) < IV_BYTES + 16 + 4:
        raise CloudPairingError("File mã hóa không hợp lệ.")
    limit = max_upload_mb * 1024 * 1024
    if len(encrypted) > limit + ENVELOPE_METADATA_LIMIT + IV_BYTES + 16 + 4:
        raise CloudPairingError(f"Tệp vượt quá {max_upload_mb} MB.")
    iv, ciphertext = encrypted[:IV_BYTES], encrypted[IV_BYTES:]
    aad = f"affiliate-report-pairing-v1:{session_id}".encode()
    try:
        plain = AESGCM(aes_key).decrypt(iv, ciphertext, aad)
    except Exception as exc:  # InvalidTag is intentionally not exposed to the UI.
        raise CloudPairingError("Không xác minh được file đã mã hóa. Hãy tạo mã QR mới.") from exc
    if len(plain) < 4:
        raise CloudPairingError("Nội dung file mã hóa không hợp lệ.")
    metadata_size = int.from_bytes(plain[:4], "big")
    if metadata_size <= 0 or metadata_size > ENVELOPE_METADATA_LIMIT or len(plain) < 4 + metadata_size:
        raise CloudPairingError("Thông tin file mã hóa không hợp lệ.")
    try:
        metadata = json.loads(plain[4 : 4 + metadata_size].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudPairingError("Thông tin file mã hóa không hợp lệ.") from exc
    data = plain[4 + metadata_size :]
    if not isinstance(metadata, dict) or metadata.get("schema") != PROTOCOL_SCHEMA:
        raise CloudPairingError("Phiên bản file mã hóa không được hỗ trợ.")
    filename = _safe_xlsx_name(str(metadata.get("filename", "")))
    if metadata.get("size") != len(data) or len(data) > limit:
        raise CloudPairingError("Dung lượng file không khớp hoặc vượt giới hạn.")
    return filename, data


class CloudPairingRunner:
    """Create one short-lived relay session and import its file in a background poller."""

    def __init__(
        self,
        *,
        nhan_tep: Callable[[str, str, bytes], dict[str, Any]],
        max_upload_mb: int,
        endpoints: Iterable[str] | None = None,
        client_factory: Callable[[str], httpx.Client] | None = None,
        poll_interval: float = 2.0,
        start_thread: bool = True,
    ) -> None:
        self._nhan_tep = nhan_tep
        self._max_upload_mb = max_upload_mb
        self._endpoints = tuple(endpoints) if endpoints is not None else relay_urls()
        if not self._endpoints:
            raise CloudPairingError("Chưa cấu hình địa chỉ Cloud Pairing.")
        for endpoint in self._endpoints:
            _validate_relay_url(endpoint)
        self._client_factory = client_factory or _http_client
        self._poll_interval = poll_interval
        self._start_thread = start_thread
        self._session: CloudPairingSession | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._so_lan_nhan = 0
        self._last_message = ""
        self._last_error = ""
        self._last_result: dict[str, Any] | None = None

    def bat(self, account: str, *, ttl: float = TOKEN_TTL_SECONDS) -> CloudPairingSession:
        self.tat()
        session_id = _token_urlsafe(24)
        upload_token = _token_urlsafe(TOKEN_BYTES)
        claim_token = _token_urlsafe(TOKEN_BYTES)
        aes_key = secrets.token_bytes(KEY_BYTES)
        request_body = {
            "schema": PROTOCOL_SCHEMA,
            "session_id": session_id,
            "upload_token_hash": hashlib.sha256(upload_token.encode()).hexdigest(),
            "claim_token_hash": hashlib.sha256(claim_token.encode()).hexdigest(),
        }
        failures: list[str] = []
        created: tuple[str, dict[str, Any]] | None = None
        for endpoint in self._endpoints:
            try:
                with self._client_factory(endpoint) as client:
                    response = client.post("/api/v1/sessions", json=request_body)
                if response.status_code != 201:
                    failures.append(_relay_detail(response))
                    continue
                payload = _json_object(response)
                if payload.get("session_id") != session_id or payload.get("state") != "created":
                    failures.append("Relay trả về phiên không khớp.")
                    continue
                created = (endpoint, payload)
                break
            except (httpx.HTTPError, ValueError) as exc:
                failures.append(type(exc).__name__)
        if created is None:
            detail = failures[-1] if failures else "Không có relay khả dụng."
            raise CloudPairingError(f"Không kết nối được Cloud Pairing. {detail}")

        endpoint, payload = created
        upload_url = str(payload.get("upload_url", "")).rstrip("/")
        if not _valid_upload_url(endpoint, upload_url, session_id):
            raise CloudPairingError("Relay trả về địa chỉ upload không hợp lệ.")
        fragment = f"k={_base64url(aes_key)}&u={quote(upload_token, safe='-_')}"
        qr_url = f"{upload_url}#{fragment}"
        session = CloudPairingSession(
            session_id=session_id,
            account=account,
            relay_url=endpoint,
            upload_url=upload_url,
            upload_token=upload_token,
            claim_token=claim_token,
            aes_key=aes_key,
            expires_at=time.monotonic() + min(float(ttl), TOKEN_TTL_SECONDS),
            qr_svg=ma_qr_svg(qr_url),
        )
        with self._lock:
            self._session = session
            self._last_message = "Đang chờ điện thoại chọn file."
            self._last_error = ""
            self._last_result = None
            self._stop.clear()
        if self._start_thread:
            self._thread = threading.Thread(target=self._poll_loop, name="pairing-cloud", daemon=True)
            self._thread.start()
        return session

    def tat(self) -> None:
        self._stop.set()
        with self._lock:
            session = self._session
            self._session = None
        if session is not None:
            self._cancel_remote(session)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        self._thread = None

    def poll_once(self) -> bool:
        """Poll once; return True when the session reached a terminal local state."""

        with self._lock:
            session = self._session
        if session is None:
            return True
        if time.monotonic() >= session.expires_at and session.phase not in {"ready", "importing"}:
            self._finish(session, error="Mã Cloud Pairing đã hết hạn. Hãy tạo mã mới.")
            return True
        try:
            with self._client_factory(session.relay_url) as client:
                response = client.get(
                    f"/api/v1/sessions/{session.session_id}",
                    headers=_claim_headers(session),
                )
            if response.status_code in {404, 410}:
                self._finish(session, error="Phiên Cloud Pairing đã hết hạn hoặc bị hủy.")
                return True
            if response.status_code != 200:
                self._set_message(session, "Cloud Pairing tạm thời chưa phản hồi; ứng dụng sẽ tự thử lại.")
                return False
            payload = _json_object(response)
            if payload.get("schema") != PROTOCOL_SCHEMA or payload.get("session_id") != session.session_id:
                self._finish(session, error="Relay trả về phiên không khớp.")
                return True
            state = str(payload.get("state", ""))
            if state == "ready":
                return self._receive(session)
            if state in {"created", "uploading"}:
                session.phase = state
                self._set_message(
                    session,
                    "Điện thoại đang gửi dữ liệu đã mã hóa…" if state == "uploading" else "Đang chờ điện thoại chọn file.",
                )
                return False
            self._finish(session, error="Relay trả về trạng thái không hợp lệ.")
            return True
        except (httpx.HTTPError, ValueError):
            self._set_message(session, "Mất kết nối cloud tạm thời; ứng dụng sẽ tự kết nối lại.")
            return False

    def trang_thai(self) -> dict[str, Any]:
        with self._lock:
            session = self._session
            result: dict[str, Any] = {
                "enabled": session is not None,
                "mode": "cloud",
                "so_lan_nhan": self._so_lan_nhan,
                "phase": session.phase if session is not None else "idle",
                "message": self._last_message,
                "error": self._last_error,
                "result": self._last_result,
            }
            if session is not None:
                result.update(
                    {
                        "account": session.account,
                        "qr_svg": session.qr_svg,
                        "expires_in": max(0, int(session.expires_at - time.monotonic())),
                        "relay_host": urlparse(session.relay_url).hostname,
                    }
                )
            return result

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            if self.poll_once():
                return
            self._stop.wait(self._poll_interval)

    def _receive(self, session: CloudPairingSession) -> bool:
        with self._lock:
            if self._session is not session or session.phase == "importing":
                return False
            session.phase = "importing"
            self._last_message = "Đang xác minh, giải mã và nhập file…"
        try:
            encrypted = self._download(session)
            filename, data = decrypt_envelope(
                session_id=session.session_id,
                aes_key=session.aes_key,
                encrypted=encrypted,
                max_upload_mb=self._max_upload_mb,
            )
            result = self._nhan_tep(session.account, filename, data)
        except (CloudPairingError, ValueError) as exc:
            self._ack_remote(session)
            self._finish(session, error=str(exc))
            return True
        except httpx.HTTPError:
            session.phase = "ready"
            self._set_message(session, "Tải file tạm thời gián đoạn; ứng dụng sẽ tự thử lại.")
            return False
        except Exception:
            # The import pipeline may reject an otherwise authentic workbook.  Keep the
            # technical exception local: the UI only needs an actionable, stable message.
            self._ack_remote(session)
            self._finish(
                session,
                error="Không nhập được file Excel. Hãy kiểm tra đúng file xuất từ TikTok rồi thử lại.",
            )
            return True

        deleted = self._ack_remote(session)
        message = "Đã nhận và nhập file từ điện thoại."
        if not deleted:
            message += " Relay sẽ tự xóa bản mã hóa khi hết hạn."
        self._finish(session, message=message, result=result, received=True)
        return True

    def _download(self, session: CloudPairingSession) -> bytes:
        max_size = self._max_upload_mb * 1024 * 1024 + ENVELOPE_METADATA_LIMIT + IV_BYTES + 20
        chunks: list[bytes] = []
        total = 0
        with self._client_factory(session.relay_url) as client:
            with client.stream(
                "GET",
                f"/api/v1/sessions/{session.session_id}/file",
                headers=_claim_headers(session),
            ) as response:
                if response.status_code != 200:
                    raise CloudPairingError(_relay_detail(response))
                try:
                    declared = int(response.headers.get("content-length", "0") or 0)
                except ValueError as exc:
                    raise CloudPairingError("Dung lượng file mã hóa không hợp lệ.") from exc
                if declared <= 0 or declared > max_size:
                    raise CloudPairingError("Dung lượng file mã hóa không hợp lệ.")
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_size:
                        raise CloudPairingError(f"Tệp vượt quá {self._max_upload_mb} MB.")
                    chunks.append(chunk)
        if total != declared:
            raise CloudPairingError("File tải về không đầy đủ.")
        return b"".join(chunks)

    def _ack_remote(self, session: CloudPairingSession) -> bool:
        try:
            with self._client_factory(session.relay_url) as client:
                response = client.post(
                    f"/api/v1/sessions/{session.session_id}/ack",
                    headers=_claim_headers(session),
                )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def _cancel_remote(self, session: CloudPairingSession) -> None:
        try:
            with self._client_factory(session.relay_url) as client:
                client.delete(f"/api/v1/sessions/{session.session_id}", headers=_claim_headers(session))
        except httpx.HTTPError:
            pass

    def _finish(
        self,
        session: CloudPairingSession,
        *,
        message: str = "",
        error: str = "",
        result: dict[str, Any] | None = None,
        received: bool = False,
    ) -> None:
        with self._lock:
            if self._session is not session:
                return
            self._session = None
            if received:
                self._so_lan_nhan += 1
            self._last_message = message
            self._last_error = error
            self._last_result = result
            self._stop.set()

    def _set_message(self, session: CloudPairingSession, message: str) -> None:
        with self._lock:
            if self._session is session:
                self._last_message = message


def _http_client(base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(12.0, connect=5.0),
        follow_redirects=False,
        headers={"user-agent": f"AffiliateReport/{APP_VERSION} CloudPairing/1"},
    )


def _claim_headers(session: CloudPairingSession) -> dict[str, str]:
    return {"authorization": f"Pairing {session.claim_token}"}


def _relay_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("error", {}).get("detail")
        if isinstance(detail, str) and detail:
            return detail
    except (ValueError, AttributeError):
        pass
    return f"Cloud relay trả về lỗi {response.status_code}."


def _json_object(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Relay response must be a JSON object")
    return payload


def _token_urlsafe(size: int) -> str:
    return _base64url(secrets.token_bytes(size))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _safe_xlsx_name(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    name = PurePosixPath(normalized).name.strip()
    if not name or not name.lower().endswith(".xlsx") or len(name.encode("utf-8")) > 512:
        raise CloudPairingError("Chỉ nhận file .xlsx có tên hợp lệ.")
    return name


def _validate_relay_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CloudPairingError("Địa chỉ Cloud Pairing phải là HTTPS hợp lệ.")
    if parsed.path not in {"", "/"}:
        raise CloudPairingError("Địa chỉ Cloud Pairing không được chứa đường dẫn.")


def _valid_upload_url(endpoint: str, upload_url: str, session_id: str) -> bool:
    expected = urlparse(endpoint)
    actual = urlparse(upload_url)
    return (
        actual.scheme == expected.scheme
        and actual.netloc == expected.netloc
        and actual.path == f"/pair/{session_id}"
        and not actual.params
        and not actual.query
        and not actual.fragment
    )
