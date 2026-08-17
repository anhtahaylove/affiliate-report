"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, AndroidUpdatePrepareResponse, AndroidUpdateSummary, CapabilityState, UpdateProgress, UpdateStatus, apiUrl, checkUpdate, installUpdate, loadAndroidUpdateStatus, loadUpdateProgress, prepareAndroidUpdate } from "@/lib/api";
import { forgetPostponedUpdate } from "@/components/update-banner";
import { ConfirmDialog } from "@/components/ui";
import { errorMessage, formatBytes, formatDateTime } from "@/lib/format";
import { ArrowRight, Check, CheckCircle2, ChevronDown, CircleAlert, CloudCog, Download, ExternalLink, HardDriveDownload, Info, MonitorUp, RefreshCw, RotateCw, ShieldCheck, Smartphone, WifiOff, type LucideIcon } from "lucide-react";
import { requestAndroidNativeDownload } from "@/lib/android-native";
import { compareSemanticVersions, deriveUpdatePresentation, type UpdateExperienceState, type UpdateIssueKind } from "@/lib/update-presentation";
import styles from "./settings-commerce.module.css";

const UPDATE_RECONNECT_TIMEOUT_MS = 90_000;
const ANDROID_APK_HANDOFF_TIMEOUT_MS = 180_000;
// Đo trên Windows: gọi tới cổng loopback đã đóng mất ~2,03 giây mới báo ConnectionRefused, chứ
// không trả lỗi ngay. Trong lúc chờ app sống lại, phần lớn thời gian mỗi vòng là chờ TCP chứ
// không phải khoảng nghỉ giữa hai lần hỏi. Cắt sớm là cách duy nhất rút ngắn được vòng đó. Khi
// app đã lên, endpoint này chỉ đọc một file JSON qua loopback nên 1,5 giây là thừa sức.
const UPDATE_PROBE_TIMEOUT_MS = 1_500;

function updateErrorInfo(reason: unknown): { kind: Exclude<UpdateIssueKind, null>; message: string; action: string } {
  if (reason instanceof ApiError) {
    if (reason.status === 0) {
      return {
        kind: "offline",
        message: "Không thể kết nối với ứng dụng để kiểm tra cập nhật.",
        action: "Mở lại Affiliate Report từ Desktop hoặc Start Menu rồi bấm “Kiểm tra lại”.",
      };
    }
    if ([401, 403].includes(reason.status)) {
      return {
        kind: "permission",
        message: "Tài khoản hiện tại không có quyền quản lý cập nhật.",
        action: "Đăng nhập bằng tài khoản Chủ sở hữu hoặc liên hệ người quản trị.",
      };
    }
    if (reason.status === 409) {
      return {
        kind: "busy",
        message: "Một phiên cập nhật đang được xử lý hoặc trạng thái chưa sẵn sàng.",
        action: "Chờ một lát rồi bấm “Kiểm tra lại”.",
      };
    }
    if ([404, 502].includes(reason.status)) {
      return {
        kind: "source",
        message: "Chưa thể kiểm tra nguồn cập nhật an toàn.",
        action: "Kiểm tra kết nối mạng rồi thử lại. Nếu lỗi tiếp diễn, hãy mở trang phát hành hoặc liên hệ người hỗ trợ.",
      };
    }
  }
  return {
    kind: "generic",
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

function updateStateCopy(state: UpdateExperienceState, targetVersion: string | null, phase: UpdateUiPhase) {
  const copy = {
    checking: { tone: "info", label: "Đang kiểm tra", title: "Đang kiểm tra phiên bản", copy: "Đang xác minh nguồn cập nhật công khai có chữ ký.", icon: RefreshCw },
    latest: { tone: "success", label: "Đã cập nhật", title: "Bạn đang dùng bản mới nhất", copy: "Không có bản mới hơn. Affiliate Report đã sẵn sàng để sử dụng.", icon: CheckCircle2 },
    available: { tone: "info", label: "Có bản mới", title: `Bản ${targetVersion ?? "mới"} đã sẵn sàng`, copy: "Ứng dụng sẽ tải, xác minh và cài đúng gói phát hành dành cho thiết bị này.", icon: Download },
    manual: { tone: "warning", label: "Cần cài thủ công", title: `Có bản ${targetVersion ?? "mới"} để tải`, copy: "Máy này chưa hỗ trợ cài tự động. Mở trang phát hành để tải đúng bộ cài.", icon: ExternalLink },
    active: { tone: "info", label: "Đang cập nhật", title: phaseLabel(phase), copy: "Giữ máy hoạt động. Ứng dụng sẽ tự đóng, cài đặt và kết nối lại.", icon: Download },
    reconnecting: { tone: "info", label: "Đang hoàn tất", title: "Đang chờ ứng dụng kết nối lại", copy: "Bộ cài đang hoàn tất và Affiliate Report sẽ tự mở lại.", icon: RotateCw },
    completed: { tone: "success", label: "Hoàn tất", title: `Đã cài xong bản ${targetVersion ?? "mới"}`, copy: "Phiên bản mới đã được xác minh và khởi động thành công.", icon: CheckCircle2 },
    failed: { tone: "danger", label: "Chưa hoàn tất", title: "Cập nhật gặp sự cố", copy: "Dữ liệu của bạn vẫn được giữ nguyên. Xem hướng xử lý bên dưới rồi thử lại.", icon: CircleAlert },
    offline: { tone: "warning", label: "Mất kết nối", title: "Chưa thể kiểm tra cập nhật", copy: "Ứng dụng không kết nối được tới dịch vụ cục bộ hoặc nguồn phát hành.", icon: WifiOff },
    issue: { tone: "warning", label: "Cần kiểm tra", title: "Cập nhật cần bạn xử lý", copy: "Xem hướng dẫn bên dưới để tiếp tục an toàn.", icon: CircleAlert },
  } satisfies Record<UpdateExperienceState, { tone: string; label: string; title: string; copy: string; icon: LucideIcon }>;
  return copy[state];
}

export function AndroidUpdateSettings({ capability, status }: { capability?: CapabilityState; status?: AndroidUpdateSummary | null }) {
  const available = capability?.available ?? Boolean(status);
  const unsupported = capability?.available === false;
  const [liveStatus, setLiveStatus] = useState<AndroidUpdateSummary | null>(status ?? null);
  const [checking, setChecking] = useState(available);
  const current = liveStatus?.current_version ?? status?.current_version ?? null;
  const published = liveStatus?.latest_version ?? null;
  const hasNewerRelease = Boolean(available && liveStatus?.available && compareSemanticVersions(published, current) === 1);
  const latest = hasNewerRelease ? published : null;
  const failed = Boolean(liveStatus?.error);
  const [preparing, setPreparing] = useState(false);
  const [prepared, setPrepared] = useState<AndroidUpdatePrepareResponse | null>(null);
  const [prepareError, setPrepareError] = useState("");

  useEffect(() => {
    if (!available) return;
    let active = true;
    void loadAndroidUpdateStatus()
      .then((next) => { if (active) setLiveStatus(next); })
      .catch((reason) => {
        if (active) setLiveStatus({
          current_version: status?.current_version ?? "—",
          available: false,
          installable: false,
          error: errorMessage(reason, "Không thể kiểm tra bản APK."),
        });
      })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, [available, status?.current_version]);

  function waitForNativeVerification(expected: AndroidUpdatePrepareResponse) {
    return new Promise<void>((resolve, reject) => {
      let timer = 0;
      const cleanup = () => {
        window.clearTimeout(timer);
        window.removeEventListener("affiliate-report-apk-ready", onReady);
        window.removeEventListener("affiliate-report-apk-error", onError);
      };
      const onReady = (event: Event) => {
        const detail = (event as CustomEvent<Record<string, unknown>>).detail ?? {};
        const size = Number(detail.size);
        const sha256 = String(detail.sha256 ?? "").toUpperCase();
        const version = String(detail.version ?? "");
        if (size !== expected.size || sha256 !== expected.sha256.toUpperCase() || version !== expected.version) {
          cleanup();
          reject(new Error("APK được Android nhận không khớp gói đã xác minh."));
          return;
        }
        cleanup();
        resolve();
      };
      const onError = (event: Event) => {
        const detail = (event as CustomEvent<{ message?: string }>).detail;
        cleanup();
        reject(new Error(detail?.message || "Android không thể xác minh APK."));
      };
      window.addEventListener("affiliate-report-apk-ready", onReady);
      window.addEventListener("affiliate-report-apk-error", onError);
      timer = window.setTimeout(() => {
        cleanup();
        reject(new Error("Android chưa xác nhận tải APK. Hãy thử lại hoặc mở trang phát hành."));
      }, ANDROID_APK_HANDOFF_TIMEOUT_MS);
    });
  }

  async function handoffAndroidUpdate() {
    setPreparing(true);
    setPrepareError("");
    setPrepared(null);
    try {
      const result = await prepareAndroidUpdate();
      const downloadUrl = new URL(result.download_url, `${apiUrl()}/`);
      if (downloadUrl.origin !== new URL(apiUrl()).origin) throw new Error("API trả về URL tải APK ngoài ứng dụng.");
      const nativeVerification = waitForNativeVerification(result);
      requestAndroidNativeDownload(
        downloadUrl.toString(),
        result.filename,
        "application/vnd.android.package-archive",
      );
      await nativeVerification;
      setPrepared(result);
    } catch (reason) {
      // Không đổi sang errorMessage() ở đây: reason luôn là Error tự ném trong hàm này (dòng 155,
      // 164, 170, 182), message đã là tiếng Việt cụ thể sẵn — errorMessage() sẽ ép về câu chung
      // chung, mất chi tiết hữu ích (vd. "APK không khớp gói đã xác minh" vs "Không thể tải APK").
      setPrepareError(reason instanceof Error ? reason.message : "Không thể tải và xác minh APK.");
    } finally {
      setPreparing(false);
    }
  }

  return (
    <section className={`${styles.surface} section ${styles.section} panel wide ${styles.wide} update-settings-page ${styles.updateSettingsPage} android-update-page`}>
      <div className={`update-overview ${styles.updateOverview}`}>
        <div className={`update-state ${styles.updateState}`} data-tone={failed || unsupported ? "warning" : hasNewerRelease ? "info" : "success"} role="status">
          <span className={`update-state-icon ${styles.updateStateIcon}`}><Smartphone size={24} aria-hidden="true" /></span>
          <div>
            <p className={`section-label ${styles.sectionLabel}`}>Ứng dụng Android</p>
            <h2>{checking ? "Đang kiểm tra bản cập nhật" : unsupported ? "Cập nhật chưa được hỗ trợ" : failed ? "Chưa kiểm tra được bản cập nhật" : hasNewerRelease ? `Có bản cập nhật ${latest} sẵn sàng` : "Bạn đang dùng bản mới nhất"}</h2>
            <p>{checking ? "Ứng dụng đang kiểm tra nguồn cập nhật có chữ ký trong nền." : unsupported ? capability?.reason : liveStatus?.error ?? liveStatus?.message ?? (available
              ? "Ứng dụng luôn kiểm tra kỹ để chắc chắn file cài đặt còn nguyên vẹn trước khi đưa vào trình cài đặt của Android."
              : capability?.reason ?? "Kênh cập nhật đang được chuẩn bị.")}</p>
          </div>
        </div>
      </div>
      <section className={`update-version-grid ${styles.updateVersionGrid}`} aria-labelledby="android-version-title">
        <h3 className={`sr-only`} id="android-version-title">Thông tin phiên bản Android</h3>
        <div><span>Đang dùng</span><strong>{current ?? "—"}</strong></div>
        <div><span>Bản khả dụng</span><strong>{latest ?? "Không có bản mới hơn"}</strong></div>
        <div><span>Cài đặt</span><strong>Android xác nhận</strong></div>
      </section>
      <div className={`update-safeguards ${styles.updateSafeguards}`}><ShieldCheck size={18} aria-hidden="true" /><p><strong>Không tự ý cài phần mềm trên máy tính</strong><span>Ứng dụng chỉ tải bản cập nhật dành cho Android; bước cài đặt cuối luôn cần bạn xác nhận trên điện thoại.</span></p></div>
      {preparing ? <div className={`android-update-progress ${styles.androidUpdateProgress}`} role="status" aria-live="polite"><progress aria-label="Đang tải và kiểm tra bản cập nhật" /><span>Đang tải và kiểm tra file cài đặt…</span></div> : null}
      {prepared ? <div className={`android-update-result ${styles.androidUpdateResult}`} role="status"><CheckCircle2 size={18} aria-hidden="true" /><span>APK {prepared.version} đã được xác minh và chuyển sang trình cài đặt Android. Hãy xác nhận cài đặt trong màn hình hệ thống.</span></div> : null}
      {prepareError ? <div className={`android-update-error ${styles.androidUpdateError}`} role="alert">{prepareError}</div> : null}
      <div className={`row-actions ${styles.rowActions} update-actions`}>
        {hasNewerRelease && liveStatus?.installable !== false ? <button className={`primary`} type="button" disabled={preparing} onClick={() => void handoffAndroidUpdate()}><Download size={16} aria-hidden="true" />{preparing ? "Đang tải và xác minh…" : "Tải và cài đặt"}</button> : null}
        {liveStatus?.release_url ? <a className={`button-link ${styles.buttonLink} secondary-link`} href={liveStatus.release_url} target="_blank" rel="noreferrer"><ExternalLink size={16} aria-hidden="true" />Xem bản phát hành</a> : null}
      </div>
    </section>
  );
}

export function UpdateSettingsPage({ checkCapability, installCapability }: { checkCapability: CapabilityState; installCapability: CapabilityState }) {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [progress, setProgress] = useState<UpdateProgress | null>(null);
  const [message, setMessage] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [issueKind, setIssueKind] = useState<UpdateIssueKind>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);
  const [busy, setBusy] = useState(checkCapability.available);
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
    setIssueKind(null);
    setMessage("");
    setNextAction("");
    setReconnecting(false);
    reconnectStartedRef.current = null;
    installStartedRef.current = null;
    try {
      const [updateStatus, updateProgress] = await Promise.all([checkUpdate(), loadUpdateProgress().catch(() => null)]);
      setStatus(updateStatus);
      rememberProgress(updateProgress);
      setLastCheckedAt(new Date().toISOString());
      const loadedPresentation = deriveUpdatePresentation({
        status: updateStatus,
        progress: updateProgress,
        busy: false,
        installing: false,
        reconnecting: false,
        issueKind: null,
        hasIssue: false,
      });
      if (updateProgress?.error && loadedPresentation.state === "failed") {
        setIssueKind("generic");
        setMessage(updateProgress.error);
        setNextAction(updateProgress.error_action || "Bấm “Kiểm tra lại”. Nếu lỗi tiếp diễn, hãy liên hệ người hỗ trợ.");
      }
    } catch (reason) {
      setStatus(null);
      rememberProgress(null);
      const issue = updateErrorInfo(reason);
      setIssueKind(issue.kind);
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
          setIssueKind("generic");
          setMessage(data.error || "Cập nhật chưa hoàn tất.");
          setNextAction(data.error_action || "Bấm “Thử lại”. Nếu lỗi tiếp diễn, hãy liên hệ người hỗ trợ.");
          return;
        }
        if (data.phase === "installed" && data.target_version && data.current_version === data.target_version) {
          installStartedRef.current = null;
          setInstalling(false);
          setBusy(false);
          if (data.error) {
            setIssueKind("generic");
            setMessage(data.error);
            setNextAction(data.error_action || "Mở lại ứng dụng rồi kiểm tra phiên bản.");
          } else {
            setIssueKind(null);
            setMessage("");
            setNextAction("");
            forgetPostponedUpdate();
            window.setTimeout(() => window.location.reload(), 1_200);
          }
          return;
        }
        setIssueKind(null);
        setNextAction("");
        setMessage("");
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
            setIssueKind("offline");
            setMessage("Ứng dụng chưa kết nối lại sau 90 giây.");
            setNextAction("Mở Affiliate Report từ Desktop hoặc Start Menu rồi bấm “Kiểm tra lại”.");
            return;
          }
          setIssueKind(null);
          setMessage("");
          timer = setTimeout(poll, Date.now() - startedAt < 10_000 ? 500 : 1_000);
          return;
        }
        setInstalling(false);
        setBusy(false);
        const issue = updateErrorInfo(reason);
        setIssueKind(issue.kind);
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
    setIssueKind(null);
    setReconnecting(false);
    reconnectStartedRef.current = null;
    installStartedRef.current = Date.now();
    rememberProgress(null);
    setMessage("");
    setNextAction("");
    try {
      const result = await installUpdate("CAP NHAT UNG DUNG");
      void result;
      setMessage("");
    } catch (reason) {
      installStartedRef.current = null;
      setInstalling(false);
      const issue = updateErrorInfo(reason);
      setIssueKind(issue.kind);
      setMessage(issue.message);
      setNextAction(issue.action);
    } finally {
      setBusy(false);
    }
  }

  const presentation = deriveUpdatePresentation({ status, progress, busy, installing, reconnecting, issueKind, hasIssue: Boolean(nextAction) });
  const phase = presentation.phase;
  const downloadValue = progress?.percent != null ? progress.percent : progress?.bytes_total ? (progress.bytes_downloaded / progress.bytes_total) * 100 : undefined;
  const targetVersion = presentation.targetVersion;
  const canInstall = Boolean(installCapability.available && presentation.state === "available" && status?.installable && status.automatic_install_supported && !installing);
  const stateCopy = updateStateCopy(presentation.state, targetVersion, phase);
  const StateIcon = stateCopy.icon;
  const messageTone = presentation.state === "failed" ? "danger" : "warning";
  const checkedText = lastCheckedAt ? formatDateTime(lastCheckedAt) : busy ? "Đang kiểm tra" : "Chưa kiểm tra";
  const showRetry = ["failed", "offline", "issue"].includes(presentation.state);

  if (!checkCapability.available) {
    return (
      <section className={`${styles.surface} section ${styles.section} panel wide ${styles.wide} capability-gate ${styles.capabilityGate}`} role="status">
        <div className={`capability-gate-icon ${styles.capabilityGateIcon}`}><CloudCog size={22} aria-hidden="true" /></div>
        <div className={`capability-gate-copy ${styles.capabilityGateCopy}`}>
          <p className={`section-label ${styles.sectionLabel}`}>Triển khai dùng chung</p>
          <h2>Phiên bản được cập nhật tại máy chủ</h2>
          <p>{checkCapability.reason}</p>
          <dl className={`capability-facts ${styles.capabilityFacts}`}>
            <div><dt><MonitorUp size={16} aria-hidden="true" />Kênh cập nhật</dt><dd>Được máy chủ tự động cập nhật</dd></div>
            <div><dt><ShieldCheck size={16} aria-hidden="true" />Ứng dụng</dt><dd>Không tự cài phần mềm trên máy này</dd></div>
          </dl>
          <p className={`hint ${styles.hint}`}>Khi người quản trị cập nhật phiên bản mới, bạn chỉ cần tải lại trang là dùng được ngay. Dữ liệu của cửa hàng không bị ảnh hưởng.</p>
        </div>
      </section>
    );
  }

  return (
    <section className={`${styles.surface} section ${styles.section} panel wide ${styles.wide} update-settings-page ${styles.updateSettingsPage} windows-update-page`} aria-busy={busy || installing || reconnecting}>
      <div className={`update-layout ${styles.updateLayout}`}>
        <div className={`update-primary-panel ${styles.updatePrimaryPanel}`}>
          <div className={`update-overview ${styles.updateOverview}`}>
            <div className={`update-state ${styles.updateState}`} data-tone={stateCopy.tone} role="status" aria-live="polite">
              <span className={`update-state-icon ${styles.updateStateIcon}`}><StateIcon size={24} aria-hidden="true" /></span>
              <div className={`update-state-copy ${styles.updateStateCopy}`}>
                <p className={`section-label ${styles.sectionLabel}`}>{stateCopy.label}</p>
                <h2>{stateCopy.title}</h2>
                <p>{stateCopy.copy}</p>
                {presentation.availableVersion && presentation.currentVersion ? <p className={`update-version-route ${styles.updateVersionRoute}`} aria-label={`Nâng từ phiên bản ${presentation.currentVersion} lên ${presentation.availableVersion}`}><strong>v{presentation.currentVersion}</strong><ArrowRight size={16} aria-hidden="true" /><strong>v{presentation.availableVersion}</strong></p> : null}
              </div>
            </div>
            <div className={`update-state-actions ${styles.updateStateActions}`}>
              {canInstall ? <button className={`primary`} type="button" onClick={() => setAskInstall(true)}><Download size={17} aria-hidden="true" />Tải và cài bản {presentation.availableVersion}</button> : null}
              {presentation.state === "manual" && status?.release_url ? <a className={`button-link ${styles.buttonLink}`} href={status.release_url} target="_blank" rel="noreferrer"><ExternalLink size={16} aria-hidden="true" />Mở trang tải</a> : null}
              {!presentation.showWorkflow && !showRetry ? <button className={`update-check-button`} type="button" onClick={() => void check()} disabled={busy || installing}>
                <RefreshCw size={17} aria-hidden="true" />{busy ? "Đang kiểm tra…" : "Kiểm tra lại"}
              </button> : null}
              {showRetry ? <button className={`primary`} type="button" onClick={() => void check()} disabled={busy}><RefreshCw size={17} aria-hidden="true" />Thử lại</button> : null}
            </div>
          </div>

          <section className={`update-version-grid ${styles.updateVersionGrid}`} aria-labelledby="update-version-title">
            <h3 className={`sr-only`} id="update-version-title">Thông tin phiên bản</h3>
            <div><span>Đang dùng</span><strong>{presentation.currentVersion ?? "—"}</strong></div>
            <div><span>Bản khả dụng</span><strong>{presentation.availabilityText}</strong></div>
            <div><span>Đã kiểm tra</span><strong>{checkedText}</strong></div>
          </section>

          {presentation.feedBehindCurrent ? <p className={`update-feed-note ${styles.updateFeedNote}`} role="status"><Info size={17} aria-hidden="true" /><span>Ứng dụng hiện tại mới hơn phiên bản nguồn đang công bố; tiến trình cũ đã được ẩn để tránh gây nhầm lẫn.</span></p> : null}

          {presentation.showWorkflow ? <section className={`update-workflow ${styles.updateWorkflow}`} aria-labelledby="update-workflow-title">
            <div className={`update-workflow-heading ${styles.updateWorkflowHeading}`}>
              <div><p className={`section-label ${styles.sectionLabel}`}>Tiến trình cập nhật</p><h3 id="update-workflow-title">{phaseLabel(phase)}{targetVersion ? ` bản ${targetVersion}` : ""}</h3></div>
              {progress?.percent != null && phase === "downloading" ? <strong>{Math.round(progress.percent)}%</strong> : null}
            </div>
            <ol className={`update-stages ${styles.updateStages}`} aria-label="Các bước cập nhật">
              {updateStages.map((stage) => {
                const StageIcon = stage.icon;
                const stageState = updateStageState(stage, phase);
                return <li key={stage.key} data-state={stageState}><span className={`update-stage-icon ${styles.updateStageIcon}`} aria-hidden="true">{stageState === "done" ? <Check size={16} /> : <StageIcon size={17} />}</span><span>{stage.label}</span></li>;
              })}
            </ol>
            {presentation.showDownloadProgress ? <div className={`download-progress ${styles.downloadProgress}`} aria-live="polite">
              <div><label htmlFor="update-download-progress">Đang tải gói cài</label><span>{progress?.bytes_total ? `${formatBytes(progress.bytes_downloaded)} / ${formatBytes(progress.bytes_total)}` : phaseLabel(phase)}{progress?.percent != null ? ` · ${Math.round(progress.percent)}%` : ""}</span></div>
              <progress id="update-download-progress" max={100} value={downloadValue} aria-valuetext={progress?.percent != null ? `${Math.round(progress.percent)} phần trăm` : undefined}>{downloadValue != null ? `${Math.round(downloadValue)}%` : undefined}</progress>
            </div> : null}
          </section> : null}

          {message ? <div className={`update-message ${styles.updateMessage}`} data-tone={messageTone} role="alert" aria-live={presentation.state === "failed" ? "assertive" : "polite"}><p>{message}</p>{nextAction ? <p><strong>Việc cần làm:</strong> {nextAction}</p> : null}</div> : null}
        </div>

        <aside className={`update-support-panel ${styles.updateSupportPanel}`} aria-label="Thông tin bản phát hành và bảo mật">
          <section className={`update-release-row ${styles.updateReleaseRow}`} aria-labelledby="update-release-title">
            <div>
              <p className={`section-label ${styles.sectionLabel}`}>Bản phát hành</p>
              <h3 id="update-release-title">{status?.release_name || (presentation.feedVersion ? `Affiliate Report ${presentation.feedVersion}` : "Chưa có thông tin")}</h3>
              <p>{status?.published_at ? `Phát hành ${formatDateTime(status.published_at)}` : "Thông tin sẽ xuất hiện sau khi kiểm tra cập nhật."}</p>
              {status?.installer_size ? <p className={`update-package-size ${styles.updatePackageSize}`}><HardDriveDownload size={16} aria-hidden="true" /><span>Gói cài Windows · {formatBytes(status.installer_size)}</span></p> : null}
            </div>
            {status?.release_url ? <a className={`button-link ${styles.buttonLink} secondary-link`} href={status.release_url} target="_blank" rel="noreferrer"><ExternalLink size={16} aria-hidden="true" />Xem bản phát hành</a> : null}
          </section>

          {status?.notes ? <details className={`update-notes ${styles.updateNotes}`}><summary><span>Ghi chú phiên bản</span><ChevronDown size={17} aria-hidden="true" /></summary><p>{status.notes}</p></details> : null}

          <details className={`update-technical ${styles.updateTechnical}`}>
            <summary><span><ShieldCheck size={18} aria-hidden="true" />Chi tiết kỹ thuật</span><ChevronDown size={17} aria-hidden="true" /></summary>
            <div className={`update-technical-body ${styles.updateTechnicalBody}`}>
              <p>Manifest được xác minh bằng Ed25519; dung lượng và SHA-256 của gói cài được kiểm tra lại trước khi chạy.</p>
              <dl>
                <div><dt>Nguồn phát hành</dt><dd className={`source-repo ${styles.sourceRepo}`}>{status?.source_repo ?? "Nguồn công khai đã ký"}</dd></div>
                <div><dt>Phiên bản trên nguồn</dt><dd>{presentation.feedVersion ?? "—"}</dd></div>
                {status?.installer_name ? <div><dt>Gói cài</dt><dd>{status.installer_name}</dd></div> : null}
                {status?.installer_size ? <div><dt>Dung lượng</dt><dd>{formatBytes(status.installer_size)}</dd></div> : null}
                {status?.bootstrap_version ? <div><dt>Updater bootstrap</dt><dd>v{status.bootstrap_version}</dd></div> : null}
              </dl>
            </div>
          </details>

          {!installCapability.available ? <p className={`hint ${styles.hint}`}>{installCapability.reason}</p> : null}
          {installCapability.available && status && !status.automatic_install_supported ? <p className={`hint ${styles.hint}`}>Cài tự động chỉ khả dụng trong bản Windows đã cài đặt.</p> : null}
        </aside>
      </div>
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
