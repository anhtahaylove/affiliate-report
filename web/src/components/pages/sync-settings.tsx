"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, CheckCircle2, Copy, DatabaseZap, History, KeyRound, LockKeyhole, RefreshCw, ServerCog, ShieldCheck, Smartphone } from "lucide-react";
import {
  type CapabilityState,
  type SyncConflictResolution,
  type SyncHistoryItem,
  type SyncPreview,
  type SyncStatus,
  exportSyncPackage,
  importSyncPackage,
  loadSyncHistory,
  loadSyncStatus,
  prepareSyncPackageExport,
  previewSyncPackage,
  apiUrl,
} from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { countsText, errorMessage, formatBytes, formatDateTime, integer } from "@/lib/format";
import { invalidateApiCache } from "@/lib/use-api";
import { requestAndroidNativeDownload } from "@/lib/android-native";

const IMPORT_CONFIRMATION = "DONG BO";
const MIN_PASSPHRASE_LENGTH = 10;

function generatePassphrase() {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const text = Array.from(bytes, (value) => alphabet[value % alphabet.length]).join("");
  return `${text.slice(0, 6)}-${text.slice(6, 12)}-${text.slice(12)}`;
}

function valueSummary(value: unknown) {
  if (value == null || value === "") return "Chưa có dữ liệu";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try { return JSON.stringify(value); }
  catch { return "Dữ liệu không đọc được"; }
}

function saveDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

function saveNativeDownload(downloadUrl: string, filename: string, expectedSize: number) {
  const origin = new URL(apiUrl()).origin;
  const url = new URL(downloadUrl, `${apiUrl()}/`);
  if (url.origin !== origin) throw new Error("API trả về URL tải gói ngoài ứng dụng.");
  return new Promise<void>((resolve, reject) => {
    let timer = 0;
    const cleanup = () => {
      window.clearTimeout(timer);
      window.removeEventListener("affiliate-report-download-ready", onReady);
      window.removeEventListener("affiliate-report-download-error", onError);
    };
    const onReady = (event: Event) => {
      const detail = (event as CustomEvent<{ source?: string; size?: number }>).detail;
      if (detail?.source !== url.toString()) return;
      cleanup();
      if (Number(detail.size) !== expectedSize) reject(new Error("File Android đã lưu không đúng dung lượng đã chuẩn bị."));
      else resolve();
    };
    const onError = (event: Event) => {
      const detail = (event as CustomEvent<{ source?: string; message?: string }>).detail;
      if (detail?.source !== url.toString()) return;
      cleanup();
      reject(new Error(detail.message || "Android không thể lưu file đồng bộ."));
    };
    window.addEventListener("affiliate-report-download-ready", onReady);
    window.addEventListener("affiliate-report-download-error", onError);
    timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("Android chưa xác nhận lưu file. Hãy thử xuất lại."));
    }, 10 * 60_000);

    try {
      requestAndroidNativeDownload(
        url.toString(),
        filename,
        "application/vnd.affiliate-report.sync",
      );
    } catch (reason) {
      cleanup();
      reject(reason);
    }
  });
}

function SyncHistory({ items }: { items: SyncHistoryItem[] }) {
  return (
    <section className="section panel wide sync-history" aria-labelledby="sync-history-title">
      <div className="section-heading">
        <div>
          <p className="section-label">Nhật ký thiết bị</p>
          <h2 id="sync-history-title">Các gói đồng bộ gần đây</h2>
          <p>Mỗi package ID chỉ được nhập một lần; nhập lại cùng gói sẽ không nhân đôi dữ liệu.</p>
        </div>
        <History size={22} aria-hidden="true" />
      </div>
      {items.length ? (
        <ol className="sync-history-list">
          {items.map((item) => (
            <li key={`${item.direction}-${item.id}`}>
              <span className="sync-direction-icon" data-direction={item.direction} aria-hidden="true">
                {item.direction === "export" ? <ArrowUpFromLine size={17} /> : <ArrowDownToLine size={17} />}
              </span>
              <div>
                <strong>{item.direction === "export" ? "Đã xuất gói" : "Đã nhập gói"}</strong>
                <span>{item.source_device?.name
                  ? `Thiết bị nguồn: ${item.source_device.name}`
                  : item.direction === "import" && item.source_device_id
                    ? `Thiết bị nguồn: ${item.source_device_id.slice(0, 8)}…`
                    : "Thiết bị này"}</span>
                <small>{countsText(item.counts)}</small>
              </div>
              <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
            </li>
          ))}
        </ol>
      ) : <p className="empty">Chưa có lần đồng bộ nào. Hãy xuất gói đầu tiên trước khi chuyển sang thiết bị khác.</p>}
    </section>
  );
}

export function SyncSettingsPage({ capability, backend, runtimePlatform }: {
  capability?: CapabilityState;
  backend: string;
  runtimePlatform?: "windows" | "android" | "web";
}) {
  // Backend cũ không có sync endpoints dù vẫn dùng SQLite; fail closed cho tới khi meta công bố capability.
  const enabled = capability?.available ?? false;
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [history, setHistory] = useState<SyncHistoryItem[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [busy, setBusy] = useState<"export" | "preview" | "import" | null>(null);
  const [message, setMessage] = useState("");
  const [exportPassphrase, setExportPassphrase] = useState("");
  const [importPassphrase, setImportPassphrase] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<SyncPreview | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, SyncConflictResolution>>({});
  const [confirming, setConfirming] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async (clearMessage = true) => {
    if (!enabled) return;
    setLoading(true);
    if (clearMessage) setMessage("");
    try {
      const [nextStatus, nextHistory] = await Promise.all([loadSyncStatus(), loadSyncHistory()]);
      setStatus(nextStatus);
      setHistory(nextHistory.items);
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể tải trạng thái đồng bộ."));
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    async function load() { await refresh(false); }
    void load();
  }, [refresh]);

  const unresolvedConflicts = useMemo(
    () => preview?.conflicts.filter((conflict) => !resolutions[conflict.id]) ?? [],
    [preview, resolutions],
  );

  if (!enabled) {
    return (
      <section className="section panel wide capability-gate" role="status">
        <div className="capability-gate-icon"><ServerCog size={22} aria-hidden="true" /></div>
        <div className="capability-gate-copy">
          <p className="section-label">Đồng bộ cục bộ</p>
          <h2>Gói đồng bộ chỉ dùng với database SQLite trên thiết bị</h2>
          <p>{capability?.reason ?? "Database hiện tại không hỗ trợ xuất và hợp nhất gói .affsync."}</p>
          <p className="hint">Ứng dụng không tải database lên Cloud Pairing hoặc bất kỳ cloud database nào.</p>
        </div>
      </section>
    );
  }

  async function copyPassphrase(value: string) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setMessage("Đã sao chép mật khẩu. Hãy gửi mật khẩu bằng kênh khác với file .affsync.");
    } catch {
      setMessage("Không thể sao chép tự động. Hãy chọn và sao chép mật khẩu thủ công.");
    }
  }

  async function exportPackage() {
    if (exportPassphrase.length < MIN_PASSPHRASE_LENGTH) {
      setMessage(`Mật khẩu xuất phải có ít nhất ${MIN_PASSPHRASE_LENGTH} ký tự.`);
      return;
    }
    setBusy("export");
    setMessage("");
    try {
      let filename: string;
      if (runtimePlatform === "android") {
        const prepared = await prepareSyncPackageExport(exportPassphrase);
        await saveNativeDownload(prepared.download_url, prepared.filename, prepared.size);
        filename = prepared.filename;
        setMessage(`Đã lưu ${filename}. Hãy giữ file và mật khẩu ở hai nơi riêng biệt.`);
      } else {
        const result = await exportSyncPackage(exportPassphrase);
        saveDownload(result.blob, result.filename);
        filename = result.filename;
        setMessage(`Đã tạo ${filename}. Hãy giữ file và mật khẩu ở hai nơi riêng biệt.`);
      }
      await refresh(false);
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể xuất gói đồng bộ."));
    } finally {
      setBusy(null);
    }
  }

  async function createPreview() {
    if (!file) return setMessage("Hãy chọn một file .affsync.");
    if (importPassphrase.length < MIN_PASSPHRASE_LENGTH) return setMessage("Hãy nhập mật khẩu của gói đồng bộ.");
    setBusy("preview");
    setMessage("");
    setPreview(null);
    setResolutions({});
    try {
      const next = await previewSyncPackage(file, importPassphrase);
      setPreview(next);
      setMessage(next.already_imported
        ? "Gói này đã được nhập trước đó; hệ thống sẽ không tạo dữ liệu trùng."
        : "Đã kiểm tra gói. Hãy xem ảnh hưởng và xử lý mọi xung đột trước khi đồng bộ.");
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể đọc gói đồng bộ. Kiểm tra lại file và mật khẩu."));
    } finally {
      setBusy(null);
    }
  }

  async function applyImport() {
    if (!preview || preview.already_imported || unresolvedConflicts.length) return;
    setBusy("import");
    setMessage("");
    try {
      const result = await importSyncPackage(preview.preview_id, resolutions, IMPORT_CONFIRMATION);
      invalidateApiCache();
      setConfirming(false);
      setPreview(null);
      setFile(null);
      setImportPassphrase("");
      setResolutions({});
      if (fileInputRef.current) fileInputRef.current.value = "";
      setMessage(result.already_imported
        ? "Gói đã có trên thiết bị; không có dữ liệu nào bị nhân đôi."
        : `Đồng bộ hoàn tất. Đã tạo bản sao lưu an toàn tại ${result.backup_path}. ${countsText(result.counts)}.`);
      await refresh(false);
    } catch (reason) {
      setMessage(errorMessage(reason, "Đồng bộ thất bại. Dữ liệu hiện tại chưa bị thay đổi."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="content-grid sync-settings-page">
      <section className="section panel wide sync-overview" aria-labelledby="sync-overview-title" aria-busy={loading}>
        <div className="section-heading">
          <div>
            <p className="section-label">Local multi-device</p>
            <h2 id="sync-overview-title">Chuyển dữ liệu an toàn giữa các thiết bị</h2>
            <p>Đây là đồng bộ thủ công, không phải cloud sync. File được mã hóa trước khi rời thiết bị và chỉ được hợp nhất sau bước xem trước.</p>
          </div>
          <button type="button" onClick={() => void refresh()} disabled={loading || busy !== null}><RefreshCw size={17} aria-hidden="true" />Làm mới</button>
        </div>
        <dl className="sync-device-facts">
          <div><dt><Smartphone size={16} aria-hidden="true" />Thiết bị này</dt><dd>{status?.device.name ?? (loading ? "Đang nhận diện…" : "Chưa xác định")}</dd></div>
          <div><dt><DatabaseZap size={16} aria-hidden="true" />Database</dt><dd>{backend}</dd></div>
          <div><dt><ShieldCheck size={16} aria-hidden="true" />Giới hạn gói</dt><dd>{formatBytes(status?.max_package_bytes ?? 100 * 1024 * 1024)}</dd></div>
          <div><dt><History size={16} aria-hidden="true" />Lịch sử</dt><dd>{integer.format(status?.history_count ?? history.length)} lần</dd></div>
        </dl>
      </section>

      <section className="section panel sync-workflow" aria-labelledby="sync-export-title">
        <div className="section-heading">
          <div><p className="section-label">Bước A · Thiết bị nguồn</p><h2 id="sync-export-title">Xuất gói mã hóa</h2><p>Tạo một snapshot nghiệp vụ để mang sang máy tính hoặc điện thoại khác.</p></div>
          <ArrowUpFromLine size={22} aria-hidden="true" />
        </div>
        <div className="sync-step-list" aria-label="Quy trình xuất">
          <span data-state="active">1. Tạo mật khẩu</span><span>2. Xuất gói</span><span>3. Chuyển file</span>
        </div>
        <div className="field">
          <label htmlFor="sync-export-passphrase">Mật khẩu mã hóa</label>
          <div className="sync-secret-control">
            <input id="sync-export-passphrase" type="text" autoComplete="off" minLength={MIN_PASSPHRASE_LENGTH} value={exportPassphrase} onChange={(event) => setExportPassphrase(event.target.value)} placeholder="Ít nhất 10 ký tự" />
            <button type="button" onClick={() => setExportPassphrase(generatePassphrase())}><KeyRound size={17} aria-hidden="true" />Tạo mật khẩu</button>
            <button type="button" onClick={() => void copyPassphrase(exportPassphrase)} disabled={!exportPassphrase}><Copy size={17} aria-hidden="true" />Sao chép</button>
          </div>
          <span>Ứng dụng không lưu mật khẩu. Nếu quên, file đã xuất không thể khôi phục.</span>
        </div>
        <button className="primary sync-primary-action" type="button" disabled={busy !== null || exportPassphrase.length < MIN_PASSPHRASE_LENGTH} onClick={() => void exportPackage()}>
          <ArrowUpFromLine size={18} aria-hidden="true" />{busy === "export" ? "Đang tạo gói…" : "Xuất file .affsync"}
        </button>
      </section>

      <section className="section panel sync-workflow" aria-labelledby="sync-import-title">
        <div className="section-heading">
          <div><p className="section-label">Bước B · Thiết bị nhận</p><h2 id="sync-import-title">Kiểm tra rồi hợp nhất</h2><p>Không ghi đè database trực tiếp. Hệ thống luôn preview, backup và kiểm tra trước khi áp dụng.</p></div>
          <ArrowDownToLine size={22} aria-hidden="true" />
        </div>
        <div className="sync-step-list" aria-label="Quy trình nhập">
          <span data-state={!preview ? "active" : "done"}>1. Chọn gói</span><span data-state={preview ? "active" : undefined}>2. Xem trước</span><span>3. Xác nhận</span>
        </div>
        <div className="field">
          <label htmlFor="sync-import-file">File đồng bộ</label>
          <div className="file-picker sync-file-picker">
            <input ref={fileInputRef} className="sr-only" id="sync-import-file" type="file" accept=".affsync,application/vnd.affiliate-report.sync,application/octet-stream" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setPreview(null); setResolutions({}); }} disabled={busy !== null} />
            <label className="file-picker-button" htmlFor="sync-import-file">Chọn file .affsync</label>
            <span>{file ? `${file.name} · ${formatBytes(file.size)}` : "Chưa chọn file"}</span>
          </div>
        </div>
        <div className="field">
          <label htmlFor="sync-import-passphrase">Mật khẩu mở gói</label>
          <input id="sync-import-passphrase" type="password" autoComplete="off" value={importPassphrase} onChange={(event) => setImportPassphrase(event.target.value)} />
        </div>
        <button type="button" disabled={busy !== null || !file || importPassphrase.length < MIN_PASSPHRASE_LENGTH} onClick={() => void createPreview()}>
          <LockKeyhole size={18} aria-hidden="true" />{busy === "preview" ? "Đang kiểm tra…" : "Mở và xem trước"}
        </button>

        {preview ? (
          <section className="sync-preview" aria-labelledby="sync-preview-title">
            <div className="record-title"><h3 id="sync-preview-title">Ảnh hưởng của gói</h3><span>{preview.source_device.name}</span></div>
            <dl className="sync-preview-facts">
              <div><dt>Package ID</dt><dd>{preview.package_id}</dd></div>
              <div><dt>Đã xuất</dt><dd>{formatDateTime(preview.exported_at)}</dd></div>
              <div><dt>Dữ liệu</dt><dd>{countsText(preview.counts)}</dd></div>
              <div><dt>Preview hết hạn</dt><dd>{formatDateTime(preview.expires_at)}</dd></div>
            </dl>
            {preview.warnings?.map((warning) => <p className="sync-warning-text" key={warning}>{warning}</p>)}
            {preview.conflicts.length ? (
              <fieldset className="sync-conflicts">
                <legend>Xử lý {integer.format(preview.conflicts.length)} xung đột</legend>
                <p>Để tránh chọn nhầm, hãy quyết định rõ từng mục. Khuyến nghị giữ dữ liệu trên thiết bị này nếu chưa chắc chắn.</p>
                {preview.conflicts.map((conflict) => (
                  <div className="sync-conflict" key={conflict.id}>
                    <div><strong>{conflict.label}</strong><small>{conflict.entity}</small></div>
                    <dl><div><dt>Thiết bị này</dt><dd>{valueSummary(conflict.local_value)}</dd></div><div><dt>Gói nhập</dt><dd>{valueSummary(conflict.incoming_value)}</dd></div></dl>
                    <label htmlFor={`sync-resolution-${conflict.id}`}>Cách xử lý</label>
                    <select id={`sync-resolution-${conflict.id}`} value={resolutions[conflict.id] ?? ""} onChange={(event) => setResolutions((current) => ({ ...current, [conflict.id]: event.target.value as SyncConflictResolution }))}>
                      <option value="">Chọn cách xử lý…</option>
                      <option value="local">Giữ dữ liệu thiết bị này</option>
                      <option value="incoming">Dùng dữ liệu từ gói</option>
                    </select>
                  </div>
                ))}
              </fieldset>
            ) : <p className="sync-ready"><CheckCircle2 size={18} aria-hidden="true" />Không có xung đột cần xử lý.</p>}
            <button className="primary sync-primary-action" type="button" onClick={() => setConfirming(true)} disabled={busy !== null || preview.already_imported || unresolvedConflicts.length > 0}>
              {unresolvedConflicts.length ? `Còn ${integer.format(unresolvedConflicts.length)} xung đột` : preview.already_imported ? "Gói đã được nhập" : "Tiếp tục đồng bộ"}
            </button>
          </section>
        ) : null}
      </section>

      {message ? <div className="sync-message wide" role="status" aria-live="polite">{message}</div> : null}
      <SyncHistory items={history} />

      <ConfirmDialog
        open={confirming}
        title="Hợp nhất dữ liệu từ gói này?"
        confirmLabel="Đồng bộ dữ liệu"
        confirmation={IMPORT_CONFIRMATION}
        busy={busy === "import"}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void applyImport()}
      >
        <p>Hệ thống sẽ tạo bản sao lưu an toàn, dựng dữ liệu trong database tạm và chỉ thay thế sau khi kiểm tra thành công.</p>
        <p className="hint">Nếu kiểm tra thất bại, database hiện tại được giữ nguyên.</p>
      </ConfirmDialog>
    </div>
  );
}
