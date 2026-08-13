"""Ghép cặp là đường duy nhất mở ra ngoài loopback, nên phần từ chối mới là phần đáng test."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tiktok_affiliate_report.pairing import (
    PairingError,
    PairingState,
    create_pair_app,
    dia_chi_ghep_cap,
    ma_qr_svg,
)

MAX_MB = 20


@pytest.fixture
def dong_ho():
    """Đồng hồ giả để tua thời gian mà không phải ngồi chờ 5 phút."""
    moc = {"t": 1000.0}
    return moc


@pytest.fixture
def state(dong_ho):
    return PairingState(port=8765, _clock=lambda: dong_ho["t"])


@pytest.fixture
def da_nhan():
    return []


@pytest.fixture
def client(state, da_nhan):
    def nhan_tep(account, filename, data):
        da_nhan.append((account, filename, len(data)))
        return {"inserted": 1}

    return TestClient(create_pair_app(state=state, nhan_tep=nhan_tep, max_upload_mb=MAX_MB))


def tep(ten="a.xlsx", noi_dung=b"xlsx"):
    return {"file": (ten, noi_dung, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def test_token_dung_duoc_thi_tep_di_vao_duong_nhap_san_co(state, client, da_nhan):
    phien = state.bat("CHIISTORE")

    r = client.post(f"/pair/{phien.token}", files=tep())

    assert r.status_code == 200
    assert da_nhan == [("CHIISTORE", "a.xlsx", 4)]


# --- Bốn trường hợp phải bị từ chối ------------------------------------------------------


def test_tu_choi_khi_token_het_han(state, client, dong_ho, da_nhan):
    phien = state.bat("CHIISTORE", ttl=300)
    dong_ho["t"] += 301

    r = client.post(f"/pair/{phien.token}", files=tep())

    assert r.status_code == 403
    assert "hết hạn" in r.json()["detail"]
    assert da_nhan == []


def test_tu_choi_khi_token_dung_lan_thu_hai(state, client, da_nhan):
    phien = state.bat("CHIISTORE")
    assert client.post(f"/pair/{phien.token}", files=tep()).status_code == 200

    r = client.post(f"/pair/{phien.token}", files=tep("b.xlsx"))

    assert r.status_code == 403
    assert "đã dùng rồi" in r.json()["detail"]
    assert len(da_nhan) == 1


def test_tu_choi_moi_route_khac_ngoai_duong_nhan_tep(state, client):
    state.bat("CHIISTORE")

    for duong_dan in ("/", "/api/v1/orders", "/api/v1/meta", "/dashboard", "/api/v1/users"):
        r = client.get(duong_dan)
        assert r.status_code == 403, duong_dan
        assert "Chỉ nhận tệp" in r.json()["detail"]


def test_tu_choi_khi_che_do_ghep_cap_dang_tat(state, client, da_nhan):
    phien = state.bat("CHIISTORE")
    state.tat()

    r = client.post(f"/pair/{phien.token}", files=tep())

    assert r.status_code == 403
    assert "đang tắt" in r.json()["detail"]
    assert da_nhan == []


# --- Ràng buộc còn lại -------------------------------------------------------------------


def test_token_la_32_ky_tu_hex_va_moi_lan_bat_lai_sinh_ma_khac(state):
    dau = state.bat("CHIISTORE").token
    sau = state.bat("CHIISTORE").token

    assert len(dau) == 32 and int(dau, 16) >= 0
    assert dau != sau
    # Bật lại làm mã cũ mất hiệu lực ngay, không để hai mã cùng sống.
    with pytest.raises(PairingError):
        state.kiem_token(dau)


def test_tu_choi_tep_khong_phai_xlsx(state, client, da_nhan):
    phien = state.bat("CHIISTORE")

    r = client.post(f"/pair/{phien.token}", files=tep("anh.jpg"))

    assert r.status_code == 415
    assert da_nhan == []


def test_tu_choi_tep_vuot_gioi_han_dung_luong(state, client, da_nhan):
    phien = state.bat("CHIISTORE")

    r = client.post(f"/pair/{phien.token}", files=tep(noi_dung=b"x" * (MAX_MB * 1024 * 1024 + 1)))

    assert r.status_code == 413
    assert da_nhan == []


def test_dia_chi_ghep_cap_va_ma_qr(state):
    state.bat("CHIISTORE")

    url = dia_chi_ghep_cap(state, host="192.168.1.50")

    assert url == f"http://192.168.1.50:8765/pair/{state.session.token}"
    svg = ma_qr_svg(url)
    assert svg.startswith("<svg") and "path" in svg
    # Không có viewBox thì đặt kích thước bằng CSS sẽ CẮT ảnh chứ không thu nhỏ: mất ô định vị
    # ở góc và điện thoại không nhận ra mã. Đúng lỗi gặp ở v2.0.21.
    assert "viewBox=" in svg


def test_dia_chi_ghep_cap_bao_loi_khi_chua_bat(state):
    with pytest.raises(PairingError):
        dia_chi_ghep_cap(state)


# --- Ba endpoint điều khiển trên app chính -----------------------------------------------


def api_client(tmp_path):
    from tiktok_affiliate_report.accounts import create_account
    from tiktok_affiliate_report.api import create_app
    from tiktok_affiliate_report.db import get_engine

    engine = get_engine(f"sqlite:///{(tmp_path / 'pairing.db').as_posix()}")
    app = create_app(engine)
    create_account(engine, "CHIISTORE", display_name="CHIISTORE")
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)), app


def test_ghep_cap_mac_dinh_tat_va_khong_mo_cong_nao(tmp_path):
    client, app = api_client(tmp_path)

    r = client.get("/api/v1/pairing")

    assert r.status_code == 200
    assert r.json() == {"enabled": False}
    # Mặc định TẮT nghĩa là chưa có gì nghe trên LAN, không phải "có nghe nhưng từ chối".
    assert getattr(app.state, "pairing").state.port == 0


def test_cong_lan_tu_dong_dong_khi_ma_het_han_khong_can_ai_hoi(monkeypatch):
    """Lỗi thật gặp trên máy người dùng ở v2.0.20.

    Việc dọn chỉ chạy khi có ai gọi /api/v1/pairing. Đóng tab trình duyệt là không còn ai gọi,
    nên socket nằm nghe trên LAN vô thời hạn dù mã đã chết. Test này KHÔNG gọi hàm dọn nào —
    chỉ đợi. Bỏ phần hẹn giờ trong PairingRunner.bat thì nó đỏ.
    """
    import socket
    import time

    from tiktok_affiliate_report.pairing import PairingRunner

    def cong_dang_mo(port: int) -> bool:
        s = socket.socket()
        s.settimeout(1)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False
        finally:
            s.close()

    runner = PairingRunner(nhan_tep=lambda *a: {}, max_upload_mb=MAX_MB)
    runner.bat("CHIISTORE", ttl=1)
    port = runner.state.port
    time.sleep(1.0)
    assert cong_dang_mo(port), "cổng phải mở trong lúc mã còn sống"

    # Chỉ đợi quá hạn. Không gọi trang thai(), không gọi don_neu_het_han().
    for _ in range(60):
        time.sleep(0.25)
        if not cong_dang_mo(port):
            break

    assert not cong_dang_mo(port), "mã hết hạn rồi mà cổng LAN vẫn nằm mở"
    runner.tat()
