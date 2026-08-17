"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, FileCheck2, FileSpreadsheet, ShieldAlert, Upload } from "lucide-react";
import { CurrentUser, ImportHistoryRow, ImportWarning, RejectedRow, UndoImportPreview, loadImportHistory, previewUndoImport, undoImport, uploadExport, visibleRejectedRows } from "@/lib/api";
import { RecentImports } from "@/components/recent-imports";
import { PairingPanel } from "@/components/pairing-panel";
import { ImportOverlapWarning } from "@/components/import-overlap-warning";
import { ConfirmDialog, canWrite, isOwner } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { errorMessage, integer } from "@/lib/format";
import type { AccountDirectory } from "@/lib/account-directory";
import styles from "./imports.module.css";

type FileOutcome = "imported" | "duplicate" | "skipped" | "failed";

type FileResult = {
  file: string;
  outcome: FileOutcome;
  detail: string;
  rejectedTotal: number;
  rejectedRows: RejectedRow[];
  warnings: ImportWarning[];
};

const OUTCOME_LABELS: Record<FileOutcome, string> = {
  imported: "Đã nhập",
  duplicate: "Đã nhập trước đó",
  skipped: "Bỏ qua",
  failed: "Lỗi",
};

// TikTok luôn xuất tệp dạng affiliate_orders<phần đuôi đổi mỗi lần xuất>.xlsx (vd.
// affiliate_orders_7674048855708600085.xlsx). Khớp affiliate_report/parser.py:FILENAME_PATTERN —
// đổi một bên mà quên bên kia thì phía không đổi vẫn nhận/chặn nhầm tệp.
const EXPORT_FILENAME_RE = /^affiliate_orders.*\.xlsx$/i;
const EXPORT_FILENAME_HINT = 'Chỉ nhận tệp .xlsx có tên bắt đầu bằng "affiliate_orders" (đúng tên TikTok xuất ra, vd. affiliate_orders_1234567890.xlsx).';

function fileSizeText(size: number) {
  if (size < 1024 * 1024) return `${integer.format(Math.max(1, Math.round(size / 1024)))} KB`;
  return `${integer.format(Math.round((size / 1024 / 1024) * 10) / 10)} MB`;
}

export function ImportsPage({ user, accounts, directory, maxUploadMb }: { user: CurrentUser; accounts: string[]; directory: AccountDirectory; maxUploadMb: number }) {
  const [account, setAccount] = useState(accounts[0] ?? "");
  const [files, setFiles] = useState<FileList | null>(null);
  const [history, setHistory] = useState<ImportHistoryRow[]>([]);
  const [message, setMessage] = useState("");
  const [results, setResults] = useState<FileResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [currentFile, setCurrentFile] = useState("");
  const [processedFiles, setProcessedFiles] = useState(0);
  const [undo, setUndo] = useState<UndoImportPreview | null>(null);
  const fileQueue = useMemo(() => Array.from(files ?? []), [files]);
  const selectedAccount = accounts.includes(account) ? account : accounts[0] ?? "";
  const refreshHistory = useCallback(async () => {
    const data = await loadImportHistory(20);
    setHistory(data.items);
  }, []);
  useEffect(() => {
    async function load() {
      try { await refreshHistory(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải lịch sử nhập.")); }
    }
    void load();
  }, [refreshHistory]);
  const hasSuccessfulResult = results.some((result) => result.outcome === "imported" || result.outcome === "duplicate");
  const invalidFiles = fileQueue.filter((file) => !EXPORT_FILENAME_RE.test(file.name)).length;
  const completedWithWarnings = results.some((result) => result.warnings.length || result.rejectedTotal || result.outcome === "failed" || result.outcome === "skipped");
  const importSteps = [
    { label: "Tài khoản", state: selectedAccount ? "done" : "active" },
    { label: "Nguồn tệp", state: fileQueue.length ? "done" : selectedAccount ? "active" : "pending" },
    { label: "Kiểm tra", state: busy || results.length ? "done" : fileQueue.length ? "active" : "pending" },
    { label: "Nhập", state: results.length ? "done" : busy ? "active" : "pending" },
    { label: "Kết quả", state: results.length ? "active" : "pending" },
  ];

  async function submit() {
    setResults([]);
    setProcessedFiles(0);
    setCurrentFile("");
    if (!canWrite(user)) return setMessage("Tài khoản chỉ xem không có quyền nhập dữ liệu.");
    if (!selectedAccount || !files?.length) return setMessage("Hãy chọn tài khoản và ít nhất một file .xlsx.");
    setBusy(true);
    setMessage("Đang chuẩn bị hàng đợi import…");
    const queued = Array.from(files);
    const collected: FileResult[] = [];
    for (const [index, file] of queued.entries()) {
      setCurrentFile(file.name);
      setMessage(`Đang xử lý file ${integer.format(index + 1)}/${integer.format(queued.length)}: ${file.name}`);
      if (!EXPORT_FILENAME_RE.test(file.name)) {
        collected.push({ file: file.name, outcome: "skipped", detail: EXPORT_FILENAME_HINT, rejectedTotal: 0, rejectedRows: [], warnings: [] });
        setProcessedFiles(index + 1);
        setResults([...collected]);
        continue;
      }
      try {
        const result = await uploadExport(selectedAccount, file);
        const imported = result.inserted + result.updated + result.unchanged;
        collected.push({
          file: file.name,
          outcome: result.duplicate ? "duplicate" : "imported",
          detail: result.duplicate
            ? "File này đã được nhập trước đó, dữ liệu không bị nhân đôi"
            : `${integer.format(result.inserted)} dòng mới · ${integer.format(result.updated)} cập nhật · ${integer.format(result.unchanged)} trùng · tổng ${integer.format(imported)} dòng`,
          rejectedTotal: result.rejected,
          rejectedRows: visibleRejectedRows(result.rejected_rows ?? []),
          warnings: result.warnings ?? [],
        });
      } catch (reason) {
        collected.push({ file: file.name, outcome: "failed", detail: errorMessage(reason, "Nhập dữ liệu thất bại."), rejectedTotal: 0, rejectedRows: [], warnings: [] });
      }
      setProcessedFiles(index + 1);
      setResults([...collected]);
    }
    invalidateApiCache();
    try {
      await refreshHistory();
      setMessage(`Hoàn tất ${integer.format(collected.length)}/${integer.format(queued.length)} file trong hàng đợi.`);
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể tải lịch sử nhập."));
    }
    setBusy(false);
    setCurrentFile("");
  }

  async function startUndo(row: ImportHistoryRow) {
    setMessage("");
    try {
      setUndo(await previewUndoImport(row.id));
    } catch (reason) {
      setUndo(null);
      setMessage(errorMessage(reason, "Không xem trước được ảnh hưởng khi hoàn tác."));
    }
  }

  async function confirmUndo() {
    if (!undo) return;
    setBusy(true);
    try {
      const result = await undoImport(undo.batch_id, undo.confirmation);
      invalidateApiCache();
      setMessage(`Đã hoàn tác ${result.filename}: gỡ ${integer.format(result.removed_lines)} dòng vừa nhập, đưa ${integer.format(result.restored_lines)} dòng bị ghi đè về đúng số liệu trước đó. Các đơn hàng khác không bị ảnh hưởng.`);
      setUndo(null);
      await refreshHistory();
    } catch (reason) {
      setMessage(errorMessage(reason, "Hoàn tác thất bại."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`${styles.pageGrid} imports-workflow-page`}>
      <section className={styles.workflow}>
        <div className={styles.sectionHeading}>
          <div>
            <p className="section-label">Nhập dữ liệu</p>
            <h2>Đưa file TikTok vào đúng tài khoản</h2>
            <p>Từng bước rõ ràng, chống nhập trùng và cảnh báo khi order + SKU có dấu hiệu nằm nhầm account.</p>
          </div>
        </div>

        <ol className={styles.stepper} aria-label="Các bước nhập dữ liệu">
          {importSteps.map((step, index) => (
            <li key={step.label} data-state={step.state} aria-current={step.state === "active" ? "step" : undefined}>
              <span>{step.state === "done" ? <Check size={14} aria-hidden="true" /> : index + 1}</span>
              <strong>{step.label}</strong>
            </li>
          ))}
        </ol>

        {!accounts.length ? <div className={`${styles.emptyState} guided-empty-state`} role="status"><div><p className="section-label">Chưa có tài khoản khả dụng</p><h3>{isOwner(user) ? "Tạo tài khoản trước khi nhập dữ liệu" : "Liên hệ chủ sở hữu để được cấp tài khoản"}</h3><p>{isOwner(user) ? "Mỗi tệp TikTok phải được gắn với một tài khoản để chống trùng và lập báo cáo đúng phạm vi." : "Bạn chưa có phạm vi tài khoản được phép nhập. Hệ thống đã khóa chọn tệp và thao tác gửi."}</p></div>{isOwner(user) ? <Link className="button-link" href="/accounts">Tạo tài khoản đầu tiên</Link> : null}</div> : <div className={styles.importStages}>
          <section className={styles.stage} aria-labelledby="import-account-title">
            <div className={styles.stageIndex}>1</div>
            <div className={styles.stageBody}>
              <div className={styles.stageHeading}><div><h3 id="import-account-title">Chọn tài khoản nhận dữ liệu</h3><p>Đây là phạm vi dùng để chống trùng và tổng hợp báo cáo.</p></div></div>
              <div className={`${styles.accountField} field`}>
                <label htmlFor="import-account">Tài khoản TikTok</label>
                <select id="import-account" value={selectedAccount} onChange={(event) => setAccount(event.target.value)} disabled={busy}>{accounts.map((item) => <option key={item} value={item}>{directory.label(item)}</option>)}</select>
              </div>
            </div>
          </section>

          <section className={styles.stage} aria-labelledby="import-source-title">
            <div className={styles.stageIndex}>2</div>
            <div className={styles.stageBody}>
              <div className={styles.stageHeading}><div><h3 id="import-source-title">Chọn nguồn tệp</h3><p>Dùng file trên máy hoặc nhận trực tiếp từ điện thoại qua LAN/Cloud Pairing.</p></div></div>
              <div className={styles.sourceGrid}>
                <div className={styles.localSource}>
                  <span className={styles.sourceKicker}><FileSpreadsheet size={15} aria-hidden="true" /> Trên thiết bị này</span>
                  <div className={`${styles.dropzone} field dropzone`}>
                    <span className="field-label">Tệp Excel đã xuất từ TikTok</span>
                    <div className={`${styles.filePicker} file-picker`}>
                      <input className="sr-only" id="import-files" aria-label="File Excel đã xuất từ TikTok" type="file" multiple accept=".xlsx" onChange={(event) => setFiles(event.target.files)} disabled={busy} />
                      <label className={styles.filePickerButton} htmlFor="import-files"><Upload size={17} aria-hidden="true" /> Chọn tệp Excel</label>
                      <span>{fileQueue.length ? `${integer.format(fileQueue.length)} tệp đã chọn` : "Chưa chọn tệp"}</span>
                    </div>
                    <span>Tối đa {integer.format(maxUploadMb)} MB/tệp. Có thể chọn nhiều file để nhập tuần tự.</span>
                  </div>
                  <p className={styles.filenameHint}>{EXPORT_FILENAME_HINT}</p>
                </div>
                {canWrite(user) ? <PairingPanel account={selectedAccount} onNhanTep={refreshHistory} /> : null}
              </div>
            </div>
          </section>

          {fileQueue.length ? (
            <section className={styles.stage} aria-labelledby="import-review-title">
              <div className={styles.stageIndex}>3</div>
              <div className={styles.stageBody}>
                <div className={styles.stageHeading}>
                  <div><h3 id="import-review-title">Kiểm tra hàng đợi</h3><p>Xác nhận tên và kích thước trước khi nhập vào {directory.label(selectedAccount)}.</p></div>
                  <span className={styles.queueCount}>{busy ? `${integer.format(processedFiles)}/${integer.format(fileQueue.length)} đã xử lý` : `${integer.format(fileQueue.length)} tệp`}</span>
                </div>
                {invalidFiles ? <p className={styles.queueWarning} role="alert"><ShieldAlert size={17} aria-hidden="true" /> {integer.format(invalidFiles)} tệp không đúng tên export và sẽ được bỏ qua.</p> : null}
                <div className={`${styles.importQueue} import-queue`} aria-live="polite">
                  <ol>
                    {fileQueue.map((file, index) => (
                      <li key={`${file.name}-${file.lastModified}`} data-state={index < processedFiles ? "done" : file.name === currentFile ? "active" : "pending"}>
                        <span className={styles.fileStateIcon}>{index < processedFiles ? <Check size={14} aria-hidden="true" /> : <FileCheck2 size={15} aria-hidden="true" />}</span>
                        <span>{file.name}</span>
                        <small>{fileSizeText(file.size)} · {EXPORT_FILENAME_RE.test(file.name) ? "Sẵn sàng" : "Sẽ bỏ qua"}</small>
                      </li>
                    ))}
                  </ol>
                </div>
                <p className={styles.safetyNote}><ShieldAlert size={17} aria-hidden="true" /> Sau khi đọc file, hệ thống so order + SKU với các account khác và cảnh báo overlap bất thường. File vẫn được lưu để không làm mất dữ liệu.</p>
                <div className={styles.importActionBar}>
                  <div><strong>Sẵn sàng nhập vào {directory.label(selectedAccount)}</strong><span>Kiểm tra lại account trước khi tiếp tục.</span></div>
                  <button className="primary" type="button" onClick={() => void submit()} disabled={busy || !selectedAccount || !fileQueue.length}>{busy ? `Đang nhập ${integer.format(processedFiles + 1)}/${integer.format(fileQueue.length)}…` : "Nhập dữ liệu"}</button>
                </div>
              </div>
            </section>
          ) : null}

          {message ? <p className={`${styles.uploadResult} upload-result`} role="status">{message}</p> : null}
          {results.length ? (
            <section className={styles.stage} aria-labelledby="import-result-title">
              <div className={styles.stageIndex}>4</div>
              <div className={styles.stageBody}>
                <div className={styles.stageHeading}><div><h3 id="import-result-title">Kết quả nhập</h3><p>{completedWithWarnings ? "Đã hoàn tất, có mục cần kiểm tra." : "Tất cả tệp đã được xử lý thành công."}</p></div></div>
                <ol className={`${styles.importResults} import-results`} aria-label="Kết quả nhập theo từng file">
                  {results.map((result) => (
                    <li key={result.file} className={`${styles.importResult} import-result`} data-outcome={result.outcome}>
                      <div className={styles.resultHeading}><strong>{result.file}</strong><span className="status-badge" data-outcome={result.outcome}>{OUTCOME_LABELS[result.outcome]}</span></div>
                      <span>{result.detail}</span>
                      <ImportOverlapWarning warnings={result.warnings} />
                      {result.rejectedTotal ? (
                        <details className={styles.rejectedDetails}>
                          <summary>{integer.format(result.rejectedTotal)} dòng bị từ chối{result.rejectedTotal > result.rejectedRows.length ? ` (hiện ${integer.format(result.rejectedRows.length)} dòng đầu)` : ""}</summary>
                          <ul>{result.rejectedRows.map((row) => <li key={`${result.file}-${row.row_number}`}>Dòng {integer.format(row.row_number)}: {row.reason}</li>)}</ul>
                        </details>
                      ) : null}
                    </li>
                  ))}
                </ol>
                {hasSuccessfulResult ? <nav className={`${styles.postActions} post-import-actions`} aria-label="Bước tiếp theo sau khi nhập"><Link className="button-link" href="/">Xem Dashboard</Link><Link className="button-link secondary-link" href="/targets">Đặt mục tiêu tháng</Link></nav> : null}
              </div>
            </section>
          ) : null}
        </div>}
      </section>
      <RecentImports rows={history} directory={directory} onUndo={(row) => void startUndo(row)} />

      <ConfirmDialog
        open={undo !== null}
        title={`Hoàn tác lần nhập ${undo?.filename ?? ""}?`}
        confirmLabel="Hoàn tác lần nhập"
        confirmation={undo?.confirmation}
        busy={busy}
        onCancel={() => setUndo(null)}
        onConfirm={() => void confirmUndo()}
      >
        <p>Hệ thống sẽ gỡ {integer.format(undo?.removed_lines ?? 0)} dòng vừa nhập, và đưa {integer.format(undo?.restored_lines ?? 0)} dòng bị ghi đè về đúng số liệu trước lần nhập này. Các đơn hàng khác không bị ảnh hưởng.</p>
        {undo?.warning ? <p className="hint">{undo.warning}</p> : null}
      </ConfirmDialog>
    </div>
  );
}
