"use client";

import { CheckCircle2, Cloud, QrCode, ShieldCheck, Smartphone, Wifi } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  loadPairingStatus,
  startPairing,
  stopPairing,
  type PairingMode,
  type PairingStatus,
} from "@/lib/api";
import { ImportOverlapWarning } from "@/components/import-overlap-warning";
import { errorMessage } from "@/lib/format";
import styles from "@/components/pages/imports.module.css";

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
  const overlapWarnings = status.result?.warnings ?? [];
  const phaseIndex = status.result ? 4 : status.phase === "importing" ? 3 : status.phase === "uploading" || status.phase === "ready" ? 2 : status.enabled ? 1 : 0;
  const transferSteps = ["Kết nối", "Quét mã", "Chọn tệp", "Nhập dữ liệu", "Hoàn tất"];

  return (
    <section className={`${styles.pairingPanel} pairing-panel`} aria-labelledby="pairing-title">
      <div className={`${styles.pairingHead} pairing-head`}>
        <div>
          <span className={styles.sourceKicker}><Smartphone size={15} aria-hidden="true" /> Điện thoại</span>
          <h2 id="pairing-title">Gửi tệp từ điện thoại</h2>
          <p className="subtle">
            Quét mã dùng một lần rồi chọn file Excel vừa xuất từ TikTok. Dữ liệu được nhập vào
            {account ? ` tài khoản ${account}` : " tài khoản đang chọn"} bằng cùng quy trình chống trùng trên máy tính.
          </p>
        </div>
        {status.enabled ? (
          <button type="button" className={styles.stopPairing} onClick={tat} disabled={busy !== null}>
            {busy === "stop" ? "Đang tắt…" : "Tắt ghép cặp"}
          </button>
        ) : null}
      </div>

      {visibleError ? <p className={styles.pairingError} role="alert">{visibleError}</p> : null}
      {!visibleError && status.message ? (
        <p className={`${styles.pairingMessage} pairing-message ${status.result ? styles.pairingSuccess : ""}`} role="status">{status.message}</p>
      ) : null}
      <ImportOverlapWarning
        warnings={overlapWarnings}
        footer="File đã được nhập để không làm mất dữ liệu. Hãy kiểm tra tài khoản đang chọn trước khi dùng báo cáo tổng."
      />

      {!status.enabled ? (
        <fieldset className={`${styles.modePicker} pairing-mode-picker`} disabled={busy !== null || !account}>
          <legend>Chọn cách kết nối</legend>
          <button type="button" className={`${styles.modeChoice} pairing-choice`} onClick={() => void bat("lan")}>
            <Wifi aria-hidden="true" size={21} strokeWidth={1.8} />
            <span>
              <span className={styles.modeTitle}><strong>Cùng Wi-Fi</strong><em>Khuyên dùng</em></span>
              <small>Nhanh nhất · tệp đi thẳng tới máy tính, không qua Internet</small>
            </span>
            <span className={`${styles.modeAction} pairing-choice-action`}>{busy === "lan" ? "Đang tạo…" : "Tạo mã QR"}</span>
          </button>
          <button type="button" className={`${styles.modeChoice} pairing-choice`} onClick={() => void bat("cloud")}>
            <Cloud aria-hidden="true" size={21} strokeWidth={1.8} />
            <span>
              <strong>Khác mạng</strong>
              <small>Dùng Cloud Relay khi điện thoại đang ở 4G/5G hoặc mạng khác</small>
            </span>
            <span className={`${styles.modeAction} pairing-choice-action`}>{busy === "cloud" ? "Đang kết nối…" : "Tạo mã QR"}</span>
          </button>
        </fieldset>
      ) : null}

      {status.enabled && status.qr_svg ? (
        <div className={`${styles.pairingBody} pairing-body`}>
          <div className={styles.qrFrame}>
            <span><QrCode size={16} aria-hidden="true" /> Quét bằng camera điện thoại</span>
            <div className={`${styles.pairingQr} pairing-qr`} aria-label={`Mã QR ghép cặp ${cloud ? "qua cloud" : "cùng Wi-Fi"}`} dangerouslySetInnerHTML={{ __html: status.qr_svg }} />
          </div>
          <div className={`${styles.pairingMeta} pairing-meta`}>
            <div className={`${styles.activeMode} pairing-active-mode`}>
              {cloud ? <Cloud aria-hidden="true" size={18} /> : <Wifi aria-hidden="true" size={18} />}
              <strong>{cloud ? "Khác mạng" : "Cùng Wi-Fi"}</strong>
            </div>
            <p className={styles.expiry}>
              Mã còn hiệu lực <strong>{phut}:{giay}</strong> và chỉ dùng được <strong>một lần</strong>.
            </p>
            <p className="hint">
              {cloud
                ? "Điện thoại có thể dùng mạng khác với máy tính (kể cả 4G/5G). Dữ liệu được mã hóa trong lúc truyền đi và chỉ máy tính này mở được — hệ thống trung chuyển ở giữa không đọc được nội dung."
                : "Điện thoại phải cùng Wi-Fi với máy tính; tệp không đi qua Internet."}
            </p>
            {cloud ? (
              <p className={`${styles.relayStatus} pairing-relay`}><ShieldCheck aria-hidden="true" size={17} /> Đường truyền: đã mã hóa qua máy chủ trung chuyển</p>
            ) : status.url ? (
              <p className="hint">Không quét được mã? Mở địa chỉ này trên trình duyệt điện thoại: <code className="pairing-url">{status.url}</code></p>
            ) : null}
            {status.message ? <p className="pairing-progress" role="status" aria-live="polite">{status.message}</p> : null}
          </div>
        </div>
      ) : null}

      {status.enabled ? (
        <ol className={styles.transferSteps} aria-label="Tiến trình nhận tệp từ điện thoại">
          {transferSteps.map((step, index) => (
            <li key={step} data-state={index < phaseIndex ? "done" : index === phaseIndex ? "active" : "pending"} aria-current={index === phaseIndex ? "step" : undefined}>
              <span>{index < phaseIndex ? <CheckCircle2 size={14} aria-hidden="true" /> : index + 1}</span>
              {step}
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
