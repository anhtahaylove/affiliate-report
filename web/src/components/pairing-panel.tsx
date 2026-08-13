"use client";

import { useCallback, useEffect, useState } from "react";
import { loadPairingStatus, startPairing, stopPairing, type PairingStatus } from "@/lib/api";
import { errorMessage } from "@/lib/format";

/**
 * Ghép cặp điện thoại: quét QR rồi gửi thẳng tệp vừa xuất từ TikTok sang máy tính.
 *
 * Mặc định TẮT, và tắt nghĩa là không có cổng nào mở trên mạng LAN. Khi bật, ứng dụng dựng
 * một listener riêng chỉ nhận tệp — không route nào khác được phục vụ ra ngoài loopback.
 */
export function PairingPanel({ account }: { account: string }) {
  const [status, setStatus] = useState<PairingStatus>({ enabled: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conLai, setConLai] = useState(0);

  const dongBo = useCallback(async () => {
    try {
      const moi = await loadPairingStatus();
      setStatus(moi);
      setConLai(moi.expires_in ?? 0);
    } catch {
      // Không báo lỗi cho việc dò trạng thái nền: người dùng chưa làm gì cả.
    }
  }, []);

  // Lấy trạng thái lần đầu theo đúng khuôn của useApi trong repo: await trước rồi mới đặt
  // state, vì gọi thẳng hàm đặt state trong effect là lỗi lint của React 19.
  useEffect(() => {
    let con_hieu_luc = true;
    void (async () => {
      const moi = await loadPairingStatus().catch(() => null);
      if (!con_hieu_luc || !moi) return;
      setStatus(moi);
      setConLai(moi.expires_in ?? 0);
    })();
    return () => {
      con_hieu_luc = false;
    };
  }, []);

  // Đếm ngược tại chỗ thay vì hỏi server mỗi giây. Hết giờ thì hỏi lại một lần để lấy trạng
  // thái thật, vì server mới là nơi quyết định mã còn sống hay không.
  useEffect(() => {
    if (!status.enabled || conLai <= 0) return;
    const dinh_gio = setTimeout(() => {
      const moi = conLai - 1;
      setConLai(moi);
      if (moi <= 0) void dongBo();
    }, 1000);
    return () => clearTimeout(dinh_gio);
  }, [status.enabled, conLai, dongBo]);

  async function doiTrangThai() {
    setBusy(true);
    setError("");
    try {
      setStatus(status.enabled ? await stopPairing() : await startPairing(account));
      if (!status.enabled) await dongBo();
    } catch (reason) {
      setError(errorMessage(reason, "Không đổi được chế độ ghép cặp."));
    } finally {
      setBusy(false);
    }
  }

  const phut = Math.floor(conLai / 60);
  const giay = String(conLai % 60).padStart(2, "0");

  return (
    <section className="panel pairing-panel">
      <div className="pairing-head">
        <div>
          <h2>Gửi tệp từ điện thoại</h2>
          <p className="subtle">
            Bật để hiện mã QR. Quét bằng điện thoại rồi chọn tệp Excel vừa xuất từ TikTok — tệp đi thẳng vào
            {account ? ` tài khoản ${account}` : " tài khoản đang chọn"}, không cần chép qua máy tính.
          </p>
        </div>
        <button type="button" className={status.enabled ? "danger-link" : "button-link"} onClick={doiTrangThai} disabled={busy || !account}>
          {busy ? "Đang xử lý…" : status.enabled ? "Tắt ghép cặp" : "Bật ghép cặp"}
        </button>
      </div>

      {error ? <p className="notice error">{error}</p> : null}

      {status.enabled && status.qr_svg ? (
        <div className="pairing-body">
          <div className="pairing-qr" aria-label="Mã QR ghép cặp" dangerouslySetInnerHTML={{ __html: status.qr_svg }} />
          <div className="pairing-meta">
            <p>
              Mã còn hiệu lực <strong>{phut}:{giay}</strong> và chỉ dùng được <strong>một lần</strong>.
            </p>
            <p className="hint">Điện thoại phải cùng mạng Wi-Fi với máy tính này.</p>
            <code className="pairing-url">{status.url}</code>
          </div>
        </div>
      ) : null}
    </section>
  );
}
