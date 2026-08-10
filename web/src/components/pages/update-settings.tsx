"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, UpdateProgress, UpdateStatus, checkUpdate, installUpdate, loadUpdateProgress } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { errorMessage, formatBytes, formatDateTime } from "@/lib/format";

function updateErrorMessage(reason: unknown) {
  const message = errorMessage(reason, "Không thể kiểm tra cập nhật.");
  if (reason instanceof ApiError && [401, 403, 404, 502].includes(reason.status)) {
    return `${message} Public signed feed không dùng token; kiểm tra URL feed, chữ ký và kết nối mạng.`;
  }
  return message;
}

type UpdateUiPhase = UpdateProgress["phase"] | "preparing";

const updateStages: Array<{ key: "check" | "download" | "verify" | "install" | "restart"; label: string; phases: UpdateUiPhase[] }> = [
  { key: "check", label: "Kiểm tra", phases: ["preparing", "idle"] },
  { key: "download", label: "Tải gói cài", phases: ["downloading"] },
  { key: "verify", label: "Xác minh", phases: ["verifying", "waiting_for_exit"] },
  { key: "install", label: "Cài đặt", phases: ["installing"] },
  { key: "restart", label: "Khởi động lại", phases: ["restarting", "installed"] },
];

const expectedDisconnectPhases: UpdateUiPhase[] = ["verifying", "waiting_for_exit", "installing", "restarting"];

function phaseLabel(phase: UpdateUiPhase) {
  return {
    preparing: "Đang chuẩn bị",
    idle: "Sẵn sàng",
    downloading: "Đang tải gói cài",
    verifying: "Đang xác minh chữ ký",
    waiting_for_exit: "Sắp đóng ứng dụng",
    installing: "Đang cài đặt",
    restarting: "Đang khởi động lại",
    installed: "Đã cài xong",
    failed: "Cập nhật lỗi",
  }[phase];
}

function updateStageState(stage: (typeof updateStages)[number], phase: UpdateUiPhase) {
  const current = updateStages.findIndex((item) => item.phases.includes(phase));
  const index = updateStages.indexOf(stage);
  if (phase === "failed") return "pending";
  if (index < current || phase === "installed") return "done";
  if (index === current) return "active";
  return "pending";
}

export function UpdateSettingsPage() {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [progress, setProgress] = useState<UpdateProgress | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [askInstall, setAskInstall] = useState(false);
  const progressRef = useRef<UpdateProgress | null>(null);
  const reconnectStartedRef = useRef<number | null>(null);
  const installStartedRef = useRef<number | null>(null);

  const rememberProgress = useCallback((data: UpdateProgress | null) => {
    progressRef.current = data;
    setProgress(data);
  }, []);

  const check = useCallback(async () => {
    setBusy(true);
    setReconnecting(false);
    reconnectStartedRef.current = null;
    installStartedRef.current = null;
    try {
      const [updateStatus, updateProgress] = await Promise.all([checkUpdate(), loadUpdateProgress().catch(() => null)]);
      setStatus(updateStatus);
      rememberProgress(updateProgress);
      setMessage(updateProgress?.phase === "failed" && updateProgress.error
        ? updateProgress.error
        : updateStatus.available
          ? `Có bản ${updateStatus.latest_version}${updateStatus.installable ? " sẵn sàng cài." : " nhưng chưa cài tự động được."}`
          : `Đang ở bản mới nhất (${updateStatus.current_version}).`);
    } catch (reason) {
      setStatus(null);
      rememberProgress(null);
      setMessage(updateErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }, [rememberProgress]);

  useEffect(() => {
    async function load() {
      await check();
    }
    void load();
  }, [check]);

  useEffect(() => {
    if (!installing) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const data = await loadUpdateProgress();
        if (stopped) return;
        rememberProgress(data);
        setReconnecting(false);
        reconnectStartedRef.current = null;
        if (data.phase === "failed") {
          installStartedRef.current = null;
          setInstalling(false);
          setBusy(false);
          setMessage(data.error || "Cập nhật thất bại. Có thể thử lại sau khi kiểm tra kết nối và gói phát hành.");
          return;
        }
        if (data.phase === "installed" && data.target_version && data.current_version === data.target_version) {
          installStartedRef.current = null;
          setInstalling(false);
          setBusy(false);
          setMessage(`Đã cài xong bản ${data.current_version}.`);
          void check();
          return;
        }
        setMessage(`${phaseLabel(data.phase)}${data.target_version ? ` bản ${data.target_version}` : ""}.`);
        timer = setTimeout(poll, 750);
      } catch (reason) {
        if (stopped) return;
        const lastPhase = progressRef.current?.phase;
        if ((lastPhase && expectedDisconnectPhases.includes(lastPhase)) || (!lastPhase && installStartedRef.current)) {
          const startedAt = reconnectStartedRef.current ?? Date.now();
          reconnectStartedRef.current = startedAt;
          setReconnecting(true);
          if (Date.now() - startedAt > 120_000) {
            setInstalling(false);
            setBusy(false);
            setMessage("Ứng dụng chưa kết nối lại sau 120 giây. Hãy mở lại ứng dụng rồi bấm kiểm tra cập nhật.");
            return;
          }
          setMessage("Ứng dụng đang đóng để cài đặt. Đang chờ kết nối lại…");
          timer = setTimeout(poll, Date.now() - startedAt < 30_000 ? 2_000 : 5_000);
          return;
        }
        setInstalling(false);
        setBusy(false);
        setMessage(updateErrorMessage(reason));
      }
    }

    timer = setTimeout(poll, 750);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [check, installing, rememberProgress]);

  async function install() {
    if (!status?.available || !status.installable || !status.automatic_install_supported) return;
    setAskInstall(false);
    setBusy(true);
    setInstalling(true);
    setReconnecting(false);
    reconnectStartedRef.current = null;
    installStartedRef.current = Date.now();
    rememberProgress(null);
    setMessage("Đang chuẩn bị cập nhật…");
    try {
      const result = await installUpdate("CAP NHAT UNG DUNG");
      setMessage(`Đã bắt đầu tải bản ${result.version}. Theo dõi tiến độ bên dưới; không đóng máy trong lúc cài.`);
    } catch (reason) {
      installStartedRef.current = null;
      setInstalling(false);
      setMessage(updateErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const phase: UpdateUiPhase = installing && !progress ? "preparing" : progress?.phase ?? "idle";
  const downloadValue = progress?.percent != null ? progress.percent : progress?.bytes_total ? (progress.bytes_downloaded / progress.bytes_total) * 100 : undefined;
  const targetVersion = progress?.target_version ?? status?.latest_version ?? null;
  const canInstall = Boolean(status?.available && status.installable && status.automatic_install_supported && !installing);

  return (
    <section className="section panel wide" aria-busy={busy || installing || reconnecting}>
      <div className="section-heading">
        <div><p className="section-label">Phiên bản ứng dụng</p><h2>Kiểm tra và cài cập nhật</h2></div>
        <button type="button" onClick={() => void check()} disabled={busy || installing}>{busy ? "Đang kiểm tra…" : "Kiểm tra cập nhật"}</button>
      </div>
      <div className="update-panel">
        <div className="update-versions"><span>Đang dùng <strong>{progress?.current_version ?? status?.current_version ?? "—"}</strong></span><span>Mới nhất <strong>{targetVersion ?? "—"}</strong></span><span>Trạng thái <strong>{phaseLabel(phase)}</strong></span></div>
        {status?.release_name ? <p><strong>{status.release_name}</strong></p> : null}
        {status?.published_at ? <p>Ngày phát hành: {formatDateTime(status.published_at)}</p> : null}
        {status?.source_repo ? <p className="source-repo">Nguồn cập nhật: {status.source_repo}</p> : null}
        {status?.notes ? <p className="update-notes" tabIndex={0}>{status.notes}</p> : null}
        {status?.release_url ? <a className="button-link secondary-link" href={status.release_url} target="_blank" rel="noreferrer">Xem trang phát hành</a> : null}
        {status && !status.automatic_install_supported ? <p className="hint">Cài tự động chỉ khả dụng trong bản Windows đã cài đặt.</p> : null}

        <div className="update-progress" aria-live="polite">
          <div className="download-progress">
            <label htmlFor="update-download-progress">Tiến độ tải gói cài</label>
            <progress id="update-download-progress" max={100} value={downloadValue}>{downloadValue ? `${Math.round(downloadValue)}%` : undefined}</progress>
            <span>{progress?.bytes_total ? `${formatBytes(progress.bytes_downloaded)} / ${formatBytes(progress.bytes_total)}` : "Chưa bắt đầu tải"}{progress?.percent != null ? ` · ${Math.round(progress.percent)}%` : ""}</span>
          </div>
          <ol className="update-stages" aria-label="Các bước cập nhật">
            {updateStages.map((stage) => <li key={stage.key} data-state={updateStageState(stage, phase)}><span aria-hidden="true" />{stage.label}</li>)}
          </ol>
        </div>

        <button className="primary" type="button" onClick={() => setAskInstall(true)} disabled={!canInstall}>Cài bản cập nhật</button>
        <p className="hint">Sau khi bắt đầu, trang này chỉ theo dõi tiến độ. Ứng dụng có thể tạm mất kết nối khi đóng để cài và khởi động lại.</p>
        {message ? <p className={phase === "failed" ? "reset-result" : "upload-result"} role="status" aria-live="polite">{message}</p> : null}
        {phase === "failed" || (!installing && message.includes("kết nối lại")) ? <button type="button" onClick={() => void check()} disabled={busy}>Thử lại kiểm tra cập nhật</button> : null}
      </div>
      <ConfirmDialog
        open={askInstall}
        title={`Cài bản ${status?.latest_version ?? ""} ngay?`}
        confirmLabel="Cài bản cập nhật"
        busy={busy}
        onCancel={() => setAskInstall(false)}
        onConfirm={() => void install()}
      >
        <p>Sau khi bắt đầu, ứng dụng sẽ tự đóng để cài đặt và không thể hủy từ trang này. Dữ liệu của bạn được giữ nguyên.</p>
      </ConfirmDialog>
    </section>
  );
}
