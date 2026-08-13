"use client";

import { Cloud, ShieldCheck, Wifi } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  loadPairingStatus,
  startPairing,
  stopPairing,
  type PairingMode,
  type PairingStatus,
} from "@/lib/api";
import { errorMessage } from "@/lib/format";

/** Hybrid Pairing: LAN là đường nhanh nhất; cloud là relay ciphertext khi hai máy khác mạng. */
export function PairingPanel({ account, onNhanTep }: { account: string; onNhanTep?: () => void }) {
  const [status, setStatus] = useState<PairingStatus>({ enabled: false });
  const [busy, setBusy] = useState<PairingMode | "stop" | null>(null);
  const [requestError, setRequestError] = useState("");
  const [conLai, setConLai] = useState(0);
  const daNhan = useRef<number | null>(null);
  const onNhanTepRef = useRef(onNhanTep);

  useEffect(() => {
    onNhanTepRef.current = onNhanTep;
  });

  const apDungTrangThai = useCallback((moi: PairingStatus) => {
    setStatus(moi);
    setConLai(moi.expires_in ?? 0);
    const truoc = daNhan.current;
    daNhan.current = moi.so_lan_nhan ?? 0;
    if (truoc !== null && (moi.so_lan_nhan ?? 0) > truoc) onNhanTepRef.current?.();
  }, []);

  const dongBo = useCallback(async () => {
    try {
      apDungTrangThai(await loadPairingStatus());
    } catch {
      // Dò nền không làm gián đoạn tác vụ; lần kế tiếp sẽ tự thử lại.
    }
  }, [apDungTrangThai]);

  useEffect(() => {
    let conHieuLuc = true;
    void (async () => {
      const moi = await loadPairingStatus().catch(() => null);
      if (conHieuLuc && moi) apDungTrangThai(moi);
    })();
    return () => {
      conHieuLuc = false;
    };
  }, [apDungTrangThai]);

  useEffect(() => {
    if (!status.enabled || conLai <= 0) return;
    const dinhGio = setTimeout(() => {
      const moi = conLai - 1;
      setConLai(moi);
      if (moi <= 0 || moi % 2 === 0) void dongBo();
    }, 1000);
    return () => clearTimeout(dinhGio);
  }, [status.enabled, conLai, dongBo]);

  async function bat(mode: PairingMode) {
    setBusy(mode);
    setRequestError("");
    try {
      apDungTrangThai(await startPairing(account, mode));
    } catch (reason) {
      setRequestError(errorMessage(reason, "Không tạo được mã ghép cặp."));
    } finally {
      setBusy(null);
    }
  }

  async function tat() {
    setBusy("stop");
    setRequestError("");
    try {
      apDungTrangThai(await stopPairing());
    } catch (reason) {
      setRequestError(errorMessage(reason, "Không tắt được ghép cặp."));
    } finally {
      setBusy(null);
    }
  }

  const phut = Math.floor(conLai / 60);
  const giay = String(conLai % 60).padStart(2, "0");
  const cloud = status.mode === "cloud";
  const visibleError = requestError || status.error || "";

  return (
    <section className="panel pairing-panel" aria-labelledby="pairing-title">
      <div className="pairing-head">
        <div>
          <h2 id="pairing-title">Gửi tệp từ điện thoại</h2>
          <p className="subtle">
            Quét một mã dùng một lần rồi chọn file Excel vừa xuất từ TikTok. Dữ liệu được nhập vào
            {account ? ` tài khoản ${account}` : " tài khoản đang chọn"} bằng cùng quy trình chống trùng trên máy tính.
          </p>
        </div>
        {status.enabled ? (
          <button type="button" className="danger-link" onClick={tat} disabled={busy !== null}>
            {busy === "stop" ? "Đang tắt…" : "Tắt ghép cặp"}
          </button>
        ) : null}
      </div>

      {visibleError ? <p className="notice error" role="alert">{visibleError}</p> : null}
      {!visibleError && status.message ? (
        <p className={`pairing-message ${status.result ? "is-success" : ""}`} role="status">{status.message}</p>
      ) : null}

      {!status.enabled ? (
        <fieldset className="pairing-mode-picker" disabled={busy !== null || !account}>
          <legend>Chọn cách kết nối</legend>
          <button type="button" className="pairing-choice" onClick={() => void bat("lan")}>
            <Wifi aria-hidden="true" size={21} strokeWidth={1.8} />
            <span>
              <strong>Cùng Wi-Fi</strong>
              <small>Nhanh nhất · file đi thẳng tới máy tính</small>
            </span>
            <span className="pairing-choice-action">{busy === "lan" ? "Đang tạo…" : "Tạo mã LAN"}</span>
          </button>
          <button type="button" className="pairing-choice" onClick={() => void bat("cloud")}>
            <Cloud aria-hidden="true" size={21} strokeWidth={1.8} />
            <span>
              <strong>Khác mạng</strong>
              <small>Dùng 4G/5G hoặc Wi-Fi khác qua Cloudflare</small>
            </span>
            <span className="pairing-choice-action">{busy === "cloud" ? "Đang kết nối…" : "Tạo mã Cloud"}</span>
          </button>
        </fieldset>
      ) : null}

      {status.enabled && status.qr_svg ? (
        <div className="pairing-body">
          <div className="pairing-qr" aria-label={`Mã QR ghép cặp ${cloud ? "qua cloud" : "cùng Wi-Fi"}`} dangerouslySetInnerHTML={{ __html: status.qr_svg }} />
          <div className="pairing-meta">
            <div className="pairing-active-mode">
              {cloud ? <Cloud aria-hidden="true" size={18} /> : <Wifi aria-hidden="true" size={18} />}
              <strong>{cloud ? "Cloud Pairing · khác mạng" : "LAN Pairing · cùng Wi-Fi"}</strong>
            </div>
            <p>
              Mã còn hiệu lực <strong>{phut}:{giay}</strong> và chỉ dùng được <strong>một lần</strong>.
            </p>
            <p className="hint">
              {cloud
                ? "Điện thoại có thể ở bất kỳ mạng nào. Relay chỉ giữ bản mã hóa ngắn hạn; khóa giải mã không rời mã QR và ứng dụng này."
                : "Điện thoại phải cùng Wi-Fi/LAN với máy tính; file không đi qua dịch vụ cloud."}
            </p>
            {cloud ? (
              <p className="pairing-relay"><ShieldCheck aria-hidden="true" size={17} /> Relay: {status.relay_host || "Cloudflare Workers"}</p>
            ) : status.url ? (
              <code className="pairing-url">{status.url}</code>
            ) : null}
            {status.message ? <p className="pairing-progress" role="status" aria-live="polite">{status.message}</p> : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
