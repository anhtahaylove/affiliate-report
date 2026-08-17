"""Ghép cặp điện thoại để tải tệp lên qua mạng LAN.

Ứng dụng bản máy bàn cố ý chỉ nghe ở 127.0.0.1 và trả 403 cho client ngoài loopback: ở chế
độ local nó tự đăng nhập quyền chủ sở hữu không cần mật khẩu, nên mở ra LAN đồng nghĩa ai
chung Wi-Fi cũng xem được số liệu tài chính.

Nên phần này KHÔNG nới lỏng bộ lọc đó. Khi bật ghép cặp, app dựng một listener riêng trên
0.0.0.0 chỉ có đúng hai route nhận tệp; mọi thứ khác không tồn tại ở đó, nên không phải tin
vào bộ lọc nào cả. Tắt ghép cặp thì listener đóng lại.

Vé vào cửa là token 32 ký tự hex, dùng một lần, sống 5 phút.
"""

from __future__ import annotations

import re
import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Callable

# Nhập ở cấp module chứ không trong hàm: "from __future__ import annotations" biến chú thích
# thành chuỗi, và pydantic không giải được ForwardRef trỏ tới tên chỉ tồn tại trong hàm.
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

TOKEN_TTL_SECONDS = 300
TOKEN_BYTES = 16  # -> 32 ký tự hex


class PairingError(Exception):
    """Từ chối một lượt ghép cặp, kèm lý do đọc được để hiện lên điện thoại."""

    def __init__(self, message: str, status_code: int = 403) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class PairingSession:
    token: str
    account: str
    expires_at: float
    used_at: float | None = None
    # Ảnh QR dựng một lần rồi dùng lại: trang Nhập dữ liệu hỏi trạng thái mỗi 2 giây, mà mã
    # không đổi trong suốt phiên. Đo được dựng lại mỗi lần tốn 7,15 ms — 150 lần một phiên.
    qr_svg: str = ""

    def con_hieu_luc(self, now: float) -> bool:
        return self.used_at is None and now < self.expires_at


@dataclass
class PairingState:
    """Giữ đúng một phiên. Bật lại lần nữa thì phiên cũ mất hiệu lực ngay."""

    session: PairingSession | None = None
    port: int = 0
    # Đếm số tệp đã nhận. Trang Nhập dữ liệu so số này giữa hai lần hỏi để biết điện thoại vừa
    # gửi xong mà tự làm mới danh sách, thay vì bắt người dùng F5.
    so_lan_nhan: int = 0
    _clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def bat(self, account: str, *, ttl: float = TOKEN_TTL_SECONDS) -> PairingSession:
        self.session = PairingSession(
            token=secrets.token_hex(TOKEN_BYTES),
            account=account,
            expires_at=self._clock() + ttl,
        )
        return self.session

    def tat(self) -> None:
        self.session = None

    def dang_bat(self) -> bool:
        return self.session is not None and self.session.con_hieu_luc(self._clock())

    def kiem_token(self, token: str) -> PairingSession:
        """Trả về phiên nếu token dùng được; ngược lại ném PairingError kèm lý do."""
        phien = self.session
        if phien is None:
            raise PairingError("Chế độ ghép cặp đang tắt.")
        # So sánh không phụ thuộc thời gian: token là vé vào cửa duy nhất.
        if not secrets.compare_digest(phien.token, token):
            raise PairingError("Mã ghép cặp không đúng.")
        if phien.used_at is not None:
            raise PairingError("Mã ghép cặp đã dùng rồi. Hãy tạo mã mới trên máy tính.")
        if self._clock() >= phien.expires_at:
            raise PairingError("Mã ghép cặp đã hết hạn. Hãy tạo mã mới trên máy tính.")
        return phien

    def danh_dau_da_dung(self, phien: PairingSession) -> None:
        phien.used_at = self._clock()
        self.so_lan_nhan += 1


def dia_chi_lan() -> str:
    """Địa chỉ LAN của máy này.

    Mở một UDP socket tới địa chỉ ngoài rồi hỏi hệ điều hành đã chọn card mạng nào — không gửi
    gói nào cả. Cách này đúng hơn gethostbyname(hostname), vốn hay trả 127.0.0.1 trên Windows
    hoặc chọn nhầm card ảo của Docker/VPN.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # TEST-NET-1, không định tuyến ra ngoài
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def dia_chi_ghep_cap(state: PairingState, *, host: str | None = None) -> str:
    if state.session is None:
        raise PairingError("Chế độ ghép cặp đang tắt.")
    return f"http://{host or dia_chi_lan()}:{state.port}/pair/{state.session.token}"


def ma_qr_svg(url: str) -> str:
    """QR dạng SVG nhúng thẳng vào trang, không cần tệp ảnh hay route riêng.

    segno chỉ ghi width/height chứ không ghi viewBox. SVG thiếu viewBox thì đặt kích thước bằng
    CSS sẽ CẮT CỤT ảnh chứ không thu nhỏ — mất mấy ô định vị ở góc là điện thoại không nhận ra
    mã nữa. Đã gặp thật ở v2.0.21. Nên phải tự thêm viewBox vào.
    """
    import segno

    buf = BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, xmldecl=False, svgns=True)
    svg = buf.getvalue().decode("utf-8")

    canh = re.search(r'width="(\d+(?:\.\d+)?)"', svg)
    if canh and "viewBox=" not in svg:
        svg = svg.replace("<svg ", f'<svg viewBox="0 0 {canh.group(1)} {canh.group(1)}" ', 1)
    return svg


def create_pair_app(
    *,
    state: PairingState,
    nhan_tep: Callable[[str, str, bytes], dict[str, Any]],
    max_upload_mb: int,
) -> Any:
    """App tối giản cho listener LAN: đúng hai route, mọi đường khác 403.

    nhan_tep(account, filename, data) đi thẳng vào đường nhập sẵn có của ứng dụng, nên giới
    hạn dung lượng, kiểm định dạng và chống trùng SHA-256 giữ nguyên như nhập từ máy tính.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(PairingError)
    async def _loi_ghep_cap(_request: Request, exc: PairingError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    @app.get("/pair/{token}", response_class=HTMLResponse)
    async def trang_tai_len(token: str) -> HTMLResponse:
        phien = state.kiem_token(token)
        return HTMLResponse(_TRANG_TAI_LEN.format(account=phien.account, token=token, mb=max_upload_mb))

    @app.post("/pair/{token}")
    async def nhan(token: str, file: UploadFile = File(...)) -> dict[str, Any]:
        phien = state.kiem_token(token)
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise HTTPException(status_code=415, detail="Chỉ nhận tệp .xlsx")
        gioi_han = max_upload_mb * 1024 * 1024
        data = await file.read(gioi_han + 1)
        if len(data) > gioi_han:
            raise HTTPException(status_code=413, detail=f"Tệp vượt quá {max_upload_mb} MB")
        # Đánh dấu đã dùng TRƯỚC khi nhập: tệp hỏng cũng tiêu mã, tránh việc thử đi thử lại
        # trên một mã còn sống. Chống trùng SHA-256 lo phần gửi lại.
        state.danh_dau_da_dung(phien)
        try:
            return nhan_tep(phien.account, file.filename or "upload.xlsx", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.api_route("/{duong_dan:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def chan_moi_thu_khac(duong_dan: str) -> JSONResponse:
        # Listener này chỉ để nhận tệp. Không có route nào khác được phục vụ ra LAN, kể cả
        # khi ai đó vô tình gắn thêm về sau.
        return JSONResponse({"detail": "Chỉ nhận tệp qua mã ghép cặp."}, status_code=403)

    return app


class PairingRunner:
    """Bật/tắt listener LAN theo trạng thái ghép cặp.

    Tắt ghép cặp là đóng hẳn socket, không chỉ từ chối request: cổng không mở thì không có gì
    để dò. Vì vậy mặc định không có gì nghe trên LAN cho tới khi người dùng bấm bật.
    """

    def __init__(
        self,
        *,
        nhan_tep: Callable[[str, str, bytes], dict[str, Any]],
        max_upload_mb: int,
        port: int = 0,
    ) -> None:
        self.state = PairingState(port=port)
        self._nhan_tep = nhan_tep
        self._max_upload_mb = max_upload_mb
        self._server: Any = None
        self._thread: Any = None
        self._hen: Any = None
        self._last_result: dict[str, Any] | None = None
        self._last_message = ""
        self._lock = threading.Lock()

    def bat(self, account: str, *, ttl: float = TOKEN_TTL_SECONDS) -> PairingSession:
        with self._lock:
            self._khoi_dong()
            self._last_result = None
            self._last_message = ""
            phien = self.state.bat(account, ttl=ttl)
            self._hen_don(ttl)
            return phien

    def tat(self) -> None:
        with self._lock:
            self.state.tat()
            self._huy_hen()
            self._dung()

    def don_neu_het_han(self) -> None:
        """Hết hạn hoặc đã dùng thì đóng cổng luôn, không đợi người dùng bấm tắt."""
        with self._lock:
            if self.state.session is not None and not self.state.dang_bat():
                self._dung()

    # Hẹn giờ đóng cổng đúng lúc mã hết hạn. Không có nó thì việc dọn chỉ xảy ra khi có ai
    # gọi /api/v1/pairing, mà đóng tab trình duyệt là không còn ai gọi — socket nằm nghe trên
    # LAN vô thời hạn dù mã đã chết. Đã gặp thật trên máy người dùng ở v2.0.20.
    def _hen_don(self, ttl: float) -> None:
        self._huy_hen()
        self._hen = threading.Timer(ttl + 1, self.don_neu_het_han)
        self._hen.daemon = True
        self._hen.start()

    def _huy_hen(self) -> None:
        hen = getattr(self, "_hen", None)
        if hen is not None:
            hen.cancel()
            self._hen = None

    def trang_thai(self) -> dict[str, Any]:
        phien = self.state.session
        if phien is None or not self.state.dang_bat():
            result: dict[str, Any] = {"enabled": False, "so_lan_nhan": self.state.so_lan_nhan}
            if self._last_result is not None:
                result.update(
                    {
                        "mode": "lan",
                        "message": self._last_message,
                        "result": self._last_result,
                    }
                )
            return result
        url = dia_chi_ghep_cap(self.state)
        if not phien.qr_svg:
            phien.qr_svg = ma_qr_svg(url)
        return {
            "enabled": True,
            "account": phien.account,
            "url": url,
            "qr_svg": phien.qr_svg,
            "expires_in": max(0, int(phien.expires_at - time.monotonic())),
            "so_lan_nhan": self.state.so_lan_nhan,
        }

    def _nhan_va_luu_ket_qua(self, account: str, filename: str, data: bytes) -> dict[str, Any]:
        """Lưu kết quả import để desktop đọc lại sau khi listener dùng một lần tự đóng."""
        result = self._nhan_tep(account, filename, data)
        with self._lock:
            self._last_result = result
            self._last_message = "Đã nhận và nhập file từ điện thoại."
        return result

    # --- phần điều khiển uvicorn ---------------------------------------------------------

    def _khoi_dong(self) -> None:
        if self._server is not None:
            return
        import uvicorn

        app = create_pair_app(
            state=self.state,
            nhan_tep=self._nhan_va_luu_ket_qua,
            max_upload_mb=self._max_upload_mb,
        )
        port = self.state.port or _cong_trong()
        self.state.port = port
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio", http="h11", log_level="warning")
        )
        self._thread = threading.Thread(target=self._server.run, name="pairing-lan", daemon=True)
        self._thread.start()

    def _dung(self) -> None:
        if self._server is None:
            return
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


def _cong_trong() -> int:
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


_TRANG_TAI_LEN = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gửi tệp TikTok</title>
<style>
 body{{font:16px/1.5 system-ui,sans-serif;margin:0;padding:24px;background:#0f1115;color:#e8eaed}}
 .the{{max-width:420px;margin:0 auto;background:#181b21;border:1px solid #2a2f3a;border-radius:14px;padding:24px}}
 h1{{font-size:20px;margin:0 0 4px}} p{{color:#9aa3b2;margin:0 0 20px}}
 input[type=file]{{width:100%;padding:14px;background:#0f1115;border:1px dashed #3a4150;border-radius:10px;color:#e8eaed}}
 button{{width:100%;margin-top:16px;padding:14px;font-size:16px;font-weight:600;border:0;border-radius:10px;background:#3b82f6;color:#fff;min-height:48px}}
 button:disabled{{opacity:.5}} .kq{{margin-top:16px;padding:12px;border-radius:10px;display:none}}
 .ok{{background:#0f2e1d;color:#6ee7a0}} .loi{{background:#33161a;color:#fca5a5}}
</style></head><body>
<div class="the">
 <h1>Gửi tệp cho {account}</h1>
 <p>Chọn tệp Excel vừa xuất từ TikTok. Tối đa {mb} MB, mã này dùng một lần.</p>
 <input id="tep" type="file" accept=".xlsx">
 <button id="gui">Gửi lên máy tính</button>
 <div id="kq" class="kq"></div>
</div>
<script>
const nut=document.getElementById('gui'),tep=document.getElementById('tep'),kq=document.getElementById('kq');
nut.onclick=async()=>{{
  if(!tep.files[0]){{hien('Hãy chọn một tệp .xlsx','loi');return;}}
  nut.disabled=true;nut.textContent='Đang gửi…';
  const fd=new FormData();fd.append('file',tep.files[0]);
  try{{
    const r=await fetch('/pair/{token}',{{method:'POST',body:fd}});
    const d=await r.json().catch(()=>({{}}));
    if(r.ok){{hien('Đã gửi xong. Xem kết quả trên máy tính.','ok');nut.textContent='Đã gửi';}}
    else{{hien(d.detail||'Gửi không thành công','loi');nut.disabled=false;nut.textContent='Gửi lên máy tính';}}
  }}catch(e){{hien('Mất kết nối tới máy tính','loi');nut.disabled=false;nut.textContent='Gửi lên máy tính';}}
}};
function hien(t,c){{kq.textContent=t;kq.className='kq '+c;kq.style.display='block';}}
</script></body></html>"""
