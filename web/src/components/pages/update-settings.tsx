"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, CapabilityState, UpdateProgress, UpdateStatus, checkUpdate, installUpdate, loadUpdateProgress } from "@/lib/api";
import { forgetPostponedUpdate } from "@/components/update-banner";
import { ConfirmDialog } from "@/components/ui";
import { formatBytes, formatDateTime } from "@/lib/format";
import { Check, CheckCircle2, CloudCog, Download, ExternalLink, HardDriveDownload, MonitorUp, RefreshCw, RotateCw, ShieldCheck, type LucideIcon } from "lucide-react";

const UPDATE_RECONNECT_TIMEOUT_MS = 90_000;
// Đo trên Windows: gọi tới cổng loopback đã đóng mất ~2,03 giây mới báo ConnectionRefused, chứ
// không trả lỗi ngay. Trong lúc chờ app sống lại, phần lớn thời gian mỗi vòng là chờ TCP chứ
// không phải khoảng nghỉ giữa hai lần hỏi. Cắt sớm là cách duy nhất rút ngắn được vòng đó. Khi
// app đã lên, endpoint này chỉ đọc một file JSON qua loopback nên 1,5 giây là thừa sức.
const UPDATE_PROBE_TIMEOUT_MS = 1_500;

function updateErrorInfo(reason: unknown) {
  if (reason instanceof ApiError) {
    if (reason.status === 0) {
      return {
        message: "Không thể kết nối với ứng dụng để kiểm tra cập nhật.",
        action: "Mở lại TikTok Affiliate Report từ Desktop hoặc Start Menu rồi bấm “Kiểm tra lại”.",
      };
    }
    if ([401, 403].includes(reason.status)) {
      return {
        message: "Tài khoản hiện tại không có quyền quản lý cập nhật.",
        action: "Đăng nhập bằng tài khoản Chủ sở hữu hoặc liên hệ người quản trị.",
      };
    }
    if (reason.status === 409) {
      return {
        message: "Một phiên cập nhật đang được xử lý hoặc trạng thái chưa sẵn sàng.",
        action: "Chờ một lát rồi bấm “Kiểm tra lại”.",
      };
    }
    if ([404, 502].includes(reason.status)) {
      return {
        message: "Chưa thể kiểm tra nguồn cập nhật an toàn.",
        action: "Kiểm tra kết nối mạng rồi thử lại. Nếu lỗi tiếp diễn, hãy mở trang phát hành hoặc liên hệ người hỗ trợ.",
      };
    }
  }
  return {
    message: "Không thể hoàn tất thao tác cập nhật.",
    action: "Bấm “Kiểm tra lại”. Nếu lỗi tiếp diễn, hãy mở trang phát hành hoặc liên hệ người hỗ trợ.",
  };
}

type UpdateUiPhase = UpdateProgress["phase"] | "preparing";

const updateStages: Array<{ key: "check" | "download" | "verify" | "install" | "restart"; label: string; icon: LucideIcon; phases: UpdateUiPhase[] }> = [
  { key: "check", label: "Kiểm tra", icon: RefreshCw, phases: ["preparing", "idle"] },
  { key: "download", label: "Tải gói cài", icon: Download, phases: ["downloading"] },
  { key: "verify", label: "Xác minh", icon: ShieldCheck, phases: ["verifying", "waiting_for_exit"] },
  { key: "install", label: "Cài đặt", icon: HardDriveDownload, phases: ["installing"] },
  { key: "restart", label: "Khởi động lại", icon: RotateCw, phases: ["restarting", "installed"] },
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

function updateStateCopy(status: UpdateStatus | null, phase: UpdateUiPhase, installing: boolean, busy: boolean, hasIssue: boolean) {
  if (phase === "failed") return { tone: "danger", title: "Cập nhật chưa hoàn tất", copy: "Kiểm tra thông báo bên dưới rồi thử lại.", icon: RotateCw };
  if (hasIssue) return { tone: "warning", title: "Cập nhật cần bạn kiểm tra", copy: "Xem việc cần làm bên dưới để hoàn tất.", icon: RotateCw };
  if (installing) return { tone: "info", title: phaseLabel(phase), copy: "Giữ ứng dụng mở; tiến trình sẽ tự kết nối lại sau khi cài đặt.", icon: Download };
  if (!status && busy) return { tone: "info", title: "Đang kiểm tra phiên bản", copy: "Đang xác minh nguồn cập nhật công khai có chữ ký.", icon: RefreshCw };
  if (status?.available) return { tone: "info", title: `Có bản ${status.latest_version} sẵn sàng`, copy: status.installable && status.automatic_install_supported ? "Bạn có thể tải, xác minh và cài ngay trong ứng dụng." : "Bản mới đã được phát hành nhưng máy này chưa hỗ trợ cài tự động.", icon: Download };
  return { tone: "success", title: "Bạn đang dùng bản mới nhất", copy: "Không cần thao tác thêm. Bạn có thể kiểm tra lại bất cứ lúc nào.", icon: CheckCircle2 };
}

export function UpdateSettingsPage({ checkCapability, installCapability }: { checkCapability: CapabilityState; installCapability: CapabilityState }) {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [progress, setProgress] = useState<UpdateProgress | null>(null);
  const [message, setMessage] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [busy, setBusy] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  // Banner "Cập nhật ngay" trỏ tới /settings/update#install để mở thẳng hộp xác nhận, thay vì
  // bắt người dùng tự tìm lại nút Cài. Đọc bằng initialiser chứ không setState trong effect
  // (React 19 cấm); `open` chỉ điều khiển showModal() nên markup không đổi, không lệch hydration.
  const [askInstall, setAskInstall] = useState(() => typeof window !== "undefined" && window.location.hash === "#install");
  const progressRef = useRef<UpdateProgress | null>(null);
  const reconnectStartedRef = useRef<number | null>(null);
  const installStartedRef = useRef<number | null>(null);

  const rememberProgress = useCallback((data: UpdateProgress | null) => {
    progressRef.current = data;
    setProgress(data);
  }, []);

  const check = useCallback(async () => {
    if (!checkCapability.available) return;
    setBusy(true);
    setReconnecting(false);
    reconnectStartedRef.current = null;
    installStartedRef.current = null;
    try {
      const [updateStatus, updateProgress] = await Promise.all([checkUpdate(), loadUpdateProgress().catch(() => null)]);
      setStatus(updateStatus);
      rememberProgress(updateProgress);
      if (updateProgress?.error) {
        setMessage(updateProgress.error);
        setNextAction(updateProgress.error_action || "Bấm “Kiểm tra lại”. Nếu lỗi tiếp diễn, hãy liên hệ người hỗ trợ.");
      } else {
        setNextAction("");
        setMessage(updateProgress?.phase === "installed" && updateProgress.target_version === updateProgress.current_version
          ? `Đã cài xong bản ${updateProgress.current_version}.`
          : updateStatus.available
            ? `Có bản ${updateStatus.latest_version}${updateStatus.installable ? " sẵn sàng cài." : " nhưng chưa cài tự động được."}`
            : `Đang ở bản mới nhất (${updateStatus.current_version}).`);
      }
    } catch (reason) {
      setStatus(null);
      rememberProgress(null);
      const issue = updateErrorInfo(reason);
      setMessage(issue.message);
      setNextAction(issue.action);
    } finally {
      setBusy(false);
    }
  }, [checkCapability.available, rememberProgress]);

  useEffect(() => {
    if (window.location.hash === "#install") {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  }, []);

  useEffect(() => {
    if (!checkCapability.available) return;
    async function load() {
      await check();
    }
    void load();
  }, [check, checkCapability.available]);

  useEffect(() => {
    if (!installing) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const data = await loadUpdateProgress(AbortSignal.timeout(UPDATE_PROBE_TIMEOUT_MS));
        if (stopped) return;
        rememberProgress(data);
        setReconnecting(false);
        reconnectStartedRef.current = null;
        if (data.phase === "failed") {
          installStartedRef.current = null;
          setInstalling(false);
          setBusy(false);
          setMessage(data.error || "Cập nhật chưa hoàn tất.");
          setNextAction(data.error_action || "Bấm “Thử lại”. Nếu lỗi tiếp diễn, hãy liên hệ người hỗ trợ.");
          return;
        }
        if (data.phase === "installed" && data.target_version && data.current_version === data.target_version) {
          installStartedRef.current = null;
          setInstalling(false);
          setBusy(false);
          if (data.error) {
            setMessage(data.error);
            setNextAction(data.error_action || "Mở lại ứng dụng rồi kiểm tra phiên bản.");
          } else {
            setMessage(`Đã cài xong bản ${data.current_version}. Đang tải lại giao diện…`);
            setNextAction("");
            forgetPostponedUpdate();
            window.setTimeout(() => window.location.reload(), 1_200);
          }
          return;
        }
        setNextAction("");
        setMessage(`${phaseLabel(data.phase)}${data.target_version ? ` bản ${data.target_version}` : ""}.`);
        timer = setTimeout(poll, 750);
      } catch (reason) {
        if (stopped) return;
        const lastPhase = progressRef.current?.phase;
        if ((lastPhase && expectedDisconnectPhases.includes(lastPhase)) || (!lastPhase && installStartedRef.current)) {
          const startedAt = reconnectStartedRef.current ?? Date.now();
          reconnectStartedRef.current = startedAt;
          setReconnecting(true);
          if (Date.now() - startedAt > UPDATE_RECONNECT_TIMEOUT_MS) {
            setInstalling(false);
            setBusy(false);
            setMessage("Ứng dụng chưa kết nối lại sau 90 giây.");
            setNextAction("Mở TikTok Affiliate Report từ Desktop hoặc Start Menu rồi bấm “Kiểm tra lại”.");
            return;
          }
          setMessage("Ứng dụng đang đóng để cài đặt. Đang chờ kết nối lại…");
          timer = setTimeout(poll, Date.now() - startedAt < 10_000 ? 500 : 1_000);
          return;
        }
        setInstalling(false);
        setBusy(false);
        const issue = updateErrorInfo(reason);
        setMessage(issue.message);
        setNextAction(issue.action);
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
    setNextAction("");
    try {
      const result = await installUpdate("CAP NHAT UNG DUNG");
      setMessage(`Đã bắt đầu tải bản ${result.version}. Theo dõi tiến độ bên dưới; không đóng máy trong lúc cài.`);
    } catch (reason) {
      installStartedRef.current = null;
      setInstalling(false);
      const issue = updateErrorInfo(reason);
      setMessage(issue.message);
      setNextAction(issue.action);
    } finally {
      setBusy(false);
    }
  }

  const phase: UpdateUiPhase = installing && !progress ? "preparing" : progress?.phase ?? "idle";
  const downloadValue = progress?.percent != null ? progress.percent : progress?.bytes_total ? (progress.bytes_downloaded / progress.bytes_total) * 100 : undefined;
  const targetVersion = progress?.target_version ?? status?.latest_version ?? null;
  const canInstall = Boolean(installCapability.available && status?.available && status.installable && status.automatic_install_supported && !installing);
  const stateCopy = updateStateCopy(status, phase, installing || reconnecting, busy, Boolean(nextAction));
  const StateIcon = stateCopy.icon;
  const showDownloadProgress = Boolean(installing || reconnecting || progress?.bytes_total || progress?.percent != null || phase === "failed" || phase === "installed");
  const messageTone = phase === "failed" ? "danger" : nextAction ? "warning" : phase === "installed" ? "success" : "info";

  if (!checkCapability.available) {
    return (
      <section className="section panel wide capability-gate" role="status">
        <div className="capability-gate-icon"><CloudCog size={22} aria-hidden="true" /></div>
        <div className="capability-gate-copy">
          <p className="section-label">Triển khai dùng chung</p>
          <h2>Phiên bản được cập nhật tại máy chủ</h2>
          <p>{checkCapability.reason}</p>
          <dl className="capability-facts">
            <div><dt><MonitorUp size={16} aria-hidden="true" />Kênh cập nhật</dt><dd>Pipeline triển khai máy chủ</dd></div>
            <div><dt><ShieldCheck size={16} aria-hidden="true" />Ứng dụng</dt><dd>Không tải hoặc chạy installer Windows</dd></div>
          </dl>
          <p className="hint">Khi quản trị viên triển khai phiên bản mới, người dùng chỉ cần tải lại trang. Dữ liệu PostgreSQL không bị thay thế bởi installer cục bộ.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="section panel wide update-settings-page" aria-busy={busy || installing || reconnecting}>
      <div className="update-overview">
        <div className="update-state" data-tone={stateCopy.tone} role="status" aria-live="polite">
          <span className="update-state-icon"><StateIcon size={24} aria-hidden="true" /></span>
          <div><p className="section-label">Trạng thái phiên bản</p><h2>{stateCopy.title}</h2><p>{stateCopy.copy}</p></div>
        </div>
        <button className="update-check-button" type="button" onClick={() => void check()} disabled={busy || installing}>
          <RefreshCw size={17} aria-hidden="true" />{busy ? "Đang kiểm tra…" : "Kiểm tra lại"}
        </button>
      </div>
      <section className="update-version-grid" aria-labelledby="update-version-title">
        <h3 className="sr-only" id="update-version-title">Thông tin phiên bản</h3>
        <div><span>Đang dùng</span><strong>{progress?.current_version ?? status?.current_version ?? "—"}</strong></div>
        <div><span>Mới nhất</span><strong>{targetVersion ?? "—"}</strong></div>
        <div><span>Tiến trình</span><strong>{phaseLabel(phase)}</strong></div>
      </section>

      <ol className="update-stages" aria-label="Các bước cập nhật">
        {updateStages.map((stage) => {
          const StageIcon = stage.icon;
          const stageState = updateStageState(stage, phase);
          return <li key={stage.key} data-state={stageState}><span className="update-stage-icon" aria-hidden="true">{stageState === "done" ? <Check size={16} /> : <StageIcon size={17} />}</span><span>{stage.label}</span></li>;
        })}
      </ol>

      {showDownloadProgress ? <div className="download-progress" aria-live="polite">
        <div><label htmlFor="update-download-progress">Tiến độ tải gói cài</label><span>{progress?.bytes_total ? `${formatBytes(progress.bytes_downloaded)} / ${formatBytes(progress.bytes_total)}` : phaseLabel(phase)}{progress?.percent != null ? ` · ${Math.round(progress.percent)}%` : ""}</span></div>
        <progress id="update-download-progress" max={100} value={downloadValue}>{downloadValue ? `${Math.round(downloadValue)}%` : undefined}</progress>
      </div> : null}

      <div className="update-release-row">
        <div>
          <p className="section-label">Bản phát hành</p>
          <h3>{status?.release_name || (targetVersion ? `TikTok Affiliate Report ${targetVersion}` : "Chưa có thông tin bản phát hành")}</h3>
          <p>{status?.published_at ? `Phát hành ${formatDateTime(status.published_at)}` : "Thông tin sẽ xuất hiện sau khi kiểm tra cập nhật."}</p>
          {status?.source_repo ? <p className="source-repo">Nguồn: {status.source_repo}</p> : null}
        </div>
        {status?.release_url ? <a className="button-link secondary-link" href={status.release_url} target="_blank" rel="noreferrer"><ExternalLink size={16} aria-hidden="true" />Xem bản phát hành</a> : null}
      </div>

      {status?.notes ? <details className="update-notes"><summary>Ghi chú phiên bản</summary><p>{status.notes}</p></details> : null}
      <div className="update-safeguards"><ShieldCheck size={18} aria-hidden="true" /><p><strong>Cập nhật an toàn</strong><span>Nguồn công khai không cần token; chữ ký và SHA-256 của gói cài được xác minh trước khi chạy.</span></p></div>
      {!installCapability.available ? <p className="hint">{installCapability.reason}</p> : null}
      {installCapability.available && status && !status.automatic_install_supported ? <p className="hint">Cài tự động chỉ khả dụng trong bản Windows đã cài đặt.</p> : null}

      <div className="row-actions update-actions">
        {canInstall ? <button className="primary" type="button" onClick={() => setAskInstall(true)}><Download size={17} aria-hidden="true" />Cài bản {status?.latest_version}</button> : null}
        {phase === "failed" || (!installing && Boolean(nextAction) && phase !== "installed") ? <button type="button" onClick={() => void check()} disabled={busy}><RefreshCw size={17} aria-hidden="true" />Thử lại</button> : null}
      </div>
      {message ? <div className="update-message" data-tone={messageTone} role={phase === "failed" || nextAction ? "alert" : "status"} aria-live={phase === "failed" ? "assertive" : "polite"}><p>{message}</p>{nextAction ? <p><strong>Việc cần làm:</strong> {nextAction}</p> : null}</div> : null}
      <ConfirmDialog
        open={askInstall && canInstall}
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
