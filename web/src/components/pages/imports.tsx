"use client";

import { useCallback, useEffect, useState } from "react";
import { CurrentUser, ImportHistoryRow, RejectedRow, UndoImportPreview, loadImportHistory, previewUndoImport, undoImport, uploadExport, visibleRejectedRows } from "@/lib/api";
import { RecentImports } from "@/components/recent-imports";
import { ConfirmDialog, canWrite } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { errorMessage, integer } from "@/lib/format";

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

export function ImportsPage({ user, accounts, maxUploadMb }: { user: CurrentUser; accounts: string[]; maxUploadMb: number }) {
  const [account, setAccount] = useState(accounts[0] ?? "");
  const [files, setFiles] = useState<FileList | null>(null);
  const [history, setHistory] = useState<ImportHistoryRow[]>([]);
  const [message, setMessage] = useState("");
  const [results, setResults] = useState<FileResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [undo, setUndo] = useState<UndoImportPreview | null>(null);
  const refreshHistory = useCallback(async () => {
    const data = await loadImportHistory(20);
    setHistory(data.items);
  }, []);
  useEffect(() => {
    async function load() {
      try { await refreshHistory(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải lịch sử import.")); }
    }
    void load();
  }, [refreshHistory]);

  async function submit() {
    setResults([]);
    if (!canWrite(user)) return setMessage("Tài khoản chỉ xem không có quyền nhập dữ liệu.");
    if (!account || !files?.length) return setMessage("Hãy chọn tài khoản và ít nhất một file .xlsx.");
    setBusy(true);
    setMessage("");
    const collected: FileResult[] = [];
    // Nhập tuần tự và ghi kết quả riêng từng file: một file lỗi không che kết quả các file khác.
    for (const file of Array.from(files)) {
      if (!file.name.toLowerCase().endsWith(".xlsx")) {
        collected.push({ file: file.name, outcome: "skipped", detail: "Không phải định dạng .xlsx", rejectedTotal: 0, rejectedRows: [] });
        continue;
      }
      try {
        const result = await uploadExport(account, file);
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
      setResults([...collected]);
    }
    invalidateApiCache();
    try {
      await refreshHistory();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể tải lịch sử import."));
    }
    setBusy(false);
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
      setMessage(`Đã hoàn tác ${result.filename}: gỡ hẳn ${integer.format(result.removed_lines)} dòng đơn, trả ${integer.format(result.restored_lines)} dòng về phiên bản trước.${result.backup_path ? ` Bản sao lưu: ${result.backup_path}.` : ""}`);
      setUndo(null);
      await refreshHistory();
    } catch (reason) {
      setMessage(errorMessage(reason, "Hoàn tác thất bại."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="content-grid">
      <section className="section panel">
        <div className="section-heading"><div><p className="section-label">Nhập tuần tự</p><h2>Chọn nhiều file TikTok</h2><p>Tối đa {integer.format(maxUploadMb)} MB mỗi file; chỉ hỗ trợ định dạng .xlsx.</p></div></div>
        <div className="upload-form">
          <div className="field"><label htmlFor="import-account">Tài khoản TikTok</label><select id="import-account" value={account} onChange={(event) => setAccount(event.target.value)}>{accounts.map((item) => <option key={item}>{item}</option>)}</select></div>
          <div className="field dropzone"><label htmlFor="import-files">File Excel đã xuất từ TikTok</label><input id="import-files" type="file" multiple accept=".xlsx" onChange={(event) => setFiles(event.target.files)} /><span>Có thể chọn nhiều file; hệ thống sẽ nhập lần lượt và tự chống trùng.</span></div>
          <button className="primary" type="button" onClick={() => void submit()} disabled={busy}>{busy ? "Đang nhập…" : "Nhập dữ liệu"}</button>
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
        </div>
      </section>
      <RecentImports rows={history} onUndo={(row) => void startUndo(row)} />

      <ConfirmDialog
        open={undo !== null}
        title={`Hoàn tác lần nhập ${undo?.filename ?? ""}?`}
        confirmLabel="Hoàn tác lần nhập"
        confirmation={undo?.confirmation}
        busy={busy}
        onCancel={() => setUndo(null)}
        onConfirm={() => void confirmUndo()}
      >
        <p>Gỡ hẳn {integer.format(undo?.removed_lines ?? 0)} dòng đơn · trả {integer.format(undo?.restored_lines ?? 0)} dòng về phiên bản trước · xoá {integer.format(undo?.removed_versions ?? 0)} bản ghi phiên bản.</p>
        {undo?.warning ? <p className="hint">{undo.warning}</p> : null}
      </ConfirmDialog>
    </div>
  );
}
