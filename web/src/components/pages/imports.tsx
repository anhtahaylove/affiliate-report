"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CurrentUser, ImportHistoryRow, RejectedRow, UndoImportPreview, loadImportHistory, previewUndoImport, undoImport, uploadExport, visibleRejectedRows } from "@/lib/api";
import { RecentImports } from "@/components/recent-imports";
import { PairingPanel } from "@/components/pairing-panel";
import { ConfirmDialog, canWrite, isOwner } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { errorMessage, integer } from "@/lib/format";
import type { AccountDirectory } from "@/lib/account-directory";

type FileOutcome = "imported" | "duplicate" | "skipped" | "failed";

type FileResult = {
  file: string;
  outcome: FileOutcome;
  detail: string;
  rejectedTotal: number;
  rejectedRows: RejectedRow[];
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
        collected.push({ file: file.name, outcome: "skipped", detail: EXPORT_FILENAME_HINT, rejectedTotal: 0, rejectedRows: [] });
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
        });
      } catch (reason) {
        collected.push({ file: file.name, outcome: "failed", detail: errorMessage(reason, "Nhập dữ liệu thất bại."), rejectedTotal: 0, rejectedRows: [] });
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
    <div className="content-grid imports-workflow-page">
      <section className="section panel">
        <div className="section-heading">
          <div>
            <p className="section-label">Nhập dữ liệu</p>
            <h2>Chọn tài khoản và tệp cần nhập</h2>
            <p>Tối đa {integer.format(maxUploadMb)} MB mỗi tệp. {EXPORT_FILENAME_HINT}</p>
          </div>
        </div>
        {canWrite(user) ? <PairingPanel account={selectedAccount} onNhanTep={refreshHistory} /> : null}
        {!accounts.length ? <div className="guided-empty-state" role="status"><div><p className="section-label">Chưa có tài khoản khả dụng</p><h3>{isOwner(user) ? "Tạo tài khoản trước khi nhập dữ liệu" : "Liên hệ chủ sở hữu để được cấp tài khoản"}</h3><p>{isOwner(user) ? "Mỗi tệp TikTok phải được gắn với một tài khoản để chống trùng và lập báo cáo đúng phạm vi." : "Bạn chưa có phạm vi tài khoản được phép nhập. Hệ thống đã khóa chọn tệp và thao tác gửi."}</p></div>{isOwner(user) ? <Link className="button-link" href="/accounts">Tạo tài khoản đầu tiên</Link> : null}</div> : <>
        <div className="upload-form">
          <div className="field">
            <label htmlFor="import-account">Tài khoản TikTok</label>
            <select id="import-account" value={selectedAccount} onChange={(event) => setAccount(event.target.value)} disabled={busy}>{accounts.map((item) => <option key={item} value={item}>{directory.label(item)}</option>)}</select>
          </div>
          <div className="field dropzone">
            <span className="field-label">Tệp Excel đã xuất từ TikTok</span>
            <div className="file-picker">
              <input className="sr-only" id="import-files" aria-label="File Excel đã xuất từ TikTok" type="file" multiple accept=".xlsx" onChange={(event) => setFiles(event.target.files)} disabled={busy} />
              <label className="file-picker-button" htmlFor="import-files">Chọn tệp Excel</label>
              <span>{fileQueue.length ? `${integer.format(fileQueue.length)} tệp đã chọn` : "Chưa chọn tệp"}</span>
            </div>
            <span>Có thể chọn nhiều tệp; hệ thống sẽ nhập lần lượt và tự chống trùng.</span>
          </div>
          {fileQueue.length ? (
            <div className="import-queue" aria-live="polite">
              <div className="record-title"><strong>Tệp đã chọn</strong><span>{busy ? `${integer.format(processedFiles)}/${integer.format(fileQueue.length)} đã xử lý` : `${integer.format(fileQueue.length)} tệp`}</span></div>
              <ol>
                {fileQueue.map((file, index) => (
                  <li key={`${file.name}-${file.lastModified}`} data-state={index < processedFiles ? "done" : file.name === currentFile ? "active" : "pending"}>
                    <span>{file.name}</span>
                    <small>{fileSizeText(file.size)} · {EXPORT_FILENAME_RE.test(file.name) ? "Sẵn sàng" : "Sẽ bỏ qua"}</small>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
          <button className="primary" type="button" onClick={() => void submit()} disabled={busy || !selectedAccount || !fileQueue.length}>{busy ? "Đang nhập…" : "Nhập dữ liệu"}</button>
          {message ? <p className="upload-result" role="status">{message}</p> : null}
          {results.length ? (
            <ol className="import-results" aria-label="Kết quả nhập theo từng file">
              {results.map((result) => (
                <li key={result.file} className="import-result" data-outcome={result.outcome}>
                  <div className="record-title"><strong>{result.file}</strong><span className="status-badge" data-outcome={result.outcome}>{OUTCOME_LABELS[result.outcome]}</span></div>
                  <span>{result.detail}</span>
                  {result.rejectedTotal ? (
                    <details>
                      <summary>{integer.format(result.rejectedTotal)} dòng bị từ chối{result.rejectedTotal > result.rejectedRows.length ? ` (hiện ${integer.format(result.rejectedRows.length)} dòng đầu)` : ""}</summary>
                      <ul>{result.rejectedRows.map((row) => <li key={`${result.file}-${row.row_number}`}>Dòng {integer.format(row.row_number)}: {row.reason}</li>)}</ul>
                    </details>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : null}
          {hasSuccessfulResult ? <nav className="post-import-actions" aria-label="Bước tiếp theo sau khi nhập"><Link className="button-link" href="/">Xem Dashboard</Link><Link className="button-link secondary-link" href="/targets">Đặt mục tiêu tháng</Link></nav> : null}
        </div>
        </>}
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
