"use client";

import { useCallback, useEffect, useState } from "react";
import { BackupItem, loadBackups, resetData, restoreBackup } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { countsText, errorMessage, formatBytes, formatDateTime } from "@/lib/format";

const RESET_PHRASE = "XOA DU LIEU";
const RESTORE_PHRASE = "KHOI PHUC DU LIEU";

export function DataSettingsPage() {
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState<"reset" | "restore" | null>(null);
  const refresh = useCallback(async () => {
    const data = await loadBackups();
    setBackups(data.items);
    setSelected((current) => current && data.items.some((item) => item.id === current) ? current : data.items[0]?.id ?? "");
  }, []);
  useEffect(() => {
    async function load() {
      try { await refresh(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải danh sách sao lưu.")); }
    }
    void load();
  }, [refresh]);
  const selectedBackup = backups.find((item) => item.id === selected);

  async function doReset() {
    setBusy(true);
    try {
      const result = await resetData(RESET_PHRASE);
      invalidateApiCache();
      setAsking(null);
      setMessage(`Đã xóa dữ liệu báo cáo. Bản sao lưu: ${result.backup_path}. Mục tiêu được giữ nguyên: ${result.targets_preserved ? "có" : "không"}.`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Xóa dữ liệu thất bại."));
    } finally {
      setBusy(false);
    }
  }

  async function doRestore() {
    if (!selectedBackup?.valid) return setMessage("Hãy chọn một bản sao lưu hợp lệ.");
    setBusy(true);
    try {
      const result = await restoreBackup(selectedBackup.id, RESTORE_PHRASE);
      invalidateApiCache();
      setAsking(null);
      setMessage(`Đã khôi phục. Bản sao lưu an toàn: ${result.safety_backup_path}. ${countsText(result.restored_counts)}.`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Khôi phục thất bại."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="content-grid">
      <section className="section danger-zone panel">
        <div className="section-heading"><div><p className="section-label danger-label">Thao tác nguy hiểm</p><h2>Xóa lịch sử báo cáo</h2><p>Tài khoản, mục tiêu và cấu hình đăng nhập vẫn được giữ lại.</p></div></div>
        <div className="reset-form">
          <button className="danger-button" type="button" onClick={() => setAsking("reset")} disabled={busy}>Xóa dữ liệu báo cáo</button>
        </div>
      </section>
      <section className="section panel">
        <div className="section-heading"><div><p className="section-label">Bản sao lưu</p><h2>Khôi phục dữ liệu</h2><p>Xem trước thời gian, dung lượng và số lượng dữ liệu trước khi khôi phục.</p></div><button type="button" onClick={() => void refresh()} disabled={busy}>Tải lại danh sách</button></div>
        <div className="reset-form">
          <div className="backup-list" role="radiogroup" aria-label="Chọn bản sao lưu">{backups.map((backup) => <label className={`backup-item${backup.valid ? "" : " invalid"}`} key={backup.id}><input type="radio" checked={selected === backup.id} onChange={() => setSelected(backup.id)} disabled={!backup.valid || busy} /><span><strong>{backup.filename}</strong><small>{formatDateTime(backup.created_at)} · {formatBytes(backup.size_bytes)} · {backup.valid ? "Hợp lệ" : backup.error}</small><small>Dữ liệu báo cáo: {countsText(backup.counts.business)}</small><small>Tài khoản trong bản sao lưu: {countsText(backup.counts.auth)}</small></span></label>)}{!backups.length ? <p className="empty">Chưa có bản sao lưu. Hệ thống sẽ tự tạo trước lần xóa dữ liệu đầu tiên.</p> : null}</div>
          <button className="danger-button" type="button" onClick={() => setAsking("restore")} disabled={busy || !selectedBackup?.valid}>Khôi phục bản sao lưu</button>
          {message ? <p className="reset-result" role="status">{message}</p> : null}
        </div>
      </section>

      <ConfirmDialog
        open={asking === "reset"}
        title="Xóa toàn bộ lịch sử nhập và dữ liệu báo cáo?"
        confirmLabel="Xóa dữ liệu báo cáo"
        confirmation={RESET_PHRASE}
        busy={busy}
        onCancel={() => setAsking(null)}
        onConfirm={() => void doReset()}
      >
        <p>Hệ thống tạo bản sao lưu đầy đủ và kiểm tra bản sao lưu đó trước khi xóa. Tài khoản, mục tiêu và cấu hình đăng nhập vẫn được giữ lại.</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={asking === "restore"}
        title={`Khôi phục ${selectedBackup?.filename ?? ""}?`}
        confirmLabel="Khôi phục bản sao lưu"
        confirmation={RESTORE_PHRASE}
        busy={busy}
        onCancel={() => setAsking(null)}
        onConfirm={() => void doRestore()}
      >
        <p>Dữ liệu hiện tại được sao lưu an toàn trước khi ghi đè.</p>
        {selectedBackup ? <p className="hint">{formatDateTime(selectedBackup.created_at)} · {formatBytes(selectedBackup.size_bytes)} · {countsText(selectedBackup.counts.business)}</p> : null}
      </ConfirmDialog>
    </div>
  );
}
