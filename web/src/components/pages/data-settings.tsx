"use client";

import { useCallback, useEffect, useState } from "react";
import { BackupItem, CapabilityState, loadBackups, resetData, restoreBackup } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { backendLabel, countsText, errorMessage, formatBytes, formatDateTime, integer } from "@/lib/format";
import { Database, ServerCog, ShieldCheck } from "lucide-react";
import styles from "./settings-commerce.module.css";

const RESET_PHRASE = "XOA DU LIEU";
const RESTORE_PHRASE = "KHOI PHUC DU LIEU";

export function DataSettingsPage({ capability, backend }: { capability: CapabilityState; backend: string }) {
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState<"reset" | "restore" | null>(null);
  const refresh = useCallback(async () => {
    if (!capability.available) return;
    const data = await loadBackups();
    setBackups(data.items);
    setSelected((current) => current && data.items.some((item) => item.id === current) ? current : data.items[0]?.id ?? "");
  }, [capability.available]);
  useEffect(() => {
    async function load() {
      if (!capability.available) return;
      try { await refresh(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải danh sách sao lưu.")); }
    }
    void load();
  }, [capability.available, refresh]);
  const selectedBackup = backups.find((item) => item.id === selected);
  const validBackups = backups.filter((backup) => backup.valid).length;

  if (!capability.available) {
    return (
      <section className={`${styles.surface} section ${styles.section} panel wide ${styles.wide} capability-gate ${styles.capabilityGate}`} role="status">
        <div className={`capability-gate-icon ${styles.capabilityGateIcon}`}><ServerCog size={22} aria-hidden="true" /></div>
        <div className={`capability-gate-copy ${styles.capabilityGateCopy}`}>
          <p className={`section-label ${styles.sectionLabel}`}>Cơ sở dữ liệu dùng chung</p>
          <h2>Sao lưu và xóa dữ liệu được quản lý ngoài ứng dụng</h2>
          <p>{capability.reason}</p>
          <dl className={`capability-facts ${styles.capabilityFacts}`}>
            <div><dt><Database size={16} aria-hidden="true" />Nơi lưu dữ liệu</dt><dd>{backendLabel(backend)}</dd></div>
            <div><dt><ShieldCheck size={16} aria-hidden="true" />Bảo vệ dữ liệu</dt><dd>Không gửi lệnh xóa hoặc khôi phục cục bộ</dd></div>
          </dl>
          <p className={`hint ${styles.hint}`}>Việc sao lưu, khôi phục hoặc xóa dữ liệu lúc này do người quản trị hệ thống của cửa hàng phụ trách. Vui lòng liên hệ người đó nếu bạn cần thao tác này.</p>
        </div>
      </section>
    );
  }

  async function doReset() {
    setBusy(true);
    try {
      const result = await resetData(RESET_PHRASE);
      invalidateApiCache();
      setAsking(null);
      setMessage(`Đã xóa dữ liệu báo cáo và tạo bản sao lưu an toàn trước khi xóa.${result.targets_preserved ? " Mục tiêu tháng của bạn vẫn được giữ nguyên." : ""}`);
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
      setMessage(`Đã khôi phục xong. Hệ thống đã tự sao lưu dữ liệu trước đó để phòng khi cần quay lại. ${countsText(result.restored_counts)}.`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Khôi phục thất bại."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`${styles.workspace} content-grid data-settings-page`}>
      <section className={`section ${styles.section} panel wide ${styles.wide} settings-overview ${styles.settingsOverview}`}>
        <div className={`section-heading ${styles.sectionHeading}`}>
          <div>
            <p className={`section-label ${styles.sectionLabel}`}>Dữ liệu & sao lưu</p>
            <h2>Bảo vệ dữ liệu trước khi ghi đè</h2>
            <p>Xóa dữ liệu và khôi phục đều yêu cầu nhập đúng cụm xác nhận; hệ thống tạo bản sao lưu an toàn trước khi ghi đè.</p>
          </div>
          <button type="button" onClick={() => void refresh()} disabled={busy}>Tải lại danh sách</button>
        </div>
        <div className={`settings-summary-row ${styles.settingsSummaryRow}`}>
          <span><strong>{integer.format(backups.length)}</strong> bản sao lưu</span>
          <span><strong>{integer.format(validBackups)}</strong> hợp lệ</span>
          <span>Đang chọn <strong>{selectedBackup?.filename ?? "—"}</strong></span>
        </div>
      </section>
      <section className={`section ${styles.section} panel`}>
        <div className={`section-heading ${styles.sectionHeading}`}><div><p className={`section-label ${styles.sectionLabel}`}>Bước 1</p><h2>Chọn bản sao lưu để khôi phục</h2><p>Xem trước thời gian, dung lượng và số lượng dữ liệu trước khi khôi phục.</p></div></div>
        <div className={`reset-form ${styles.resetForm}`}>
          <div className={`backup-list ${styles.backupList}`} role="radiogroup" aria-label="Chọn bản sao lưu">{backups.map((backup) => <label className={`backup-item ${styles.backupItem}`} data-invalid={backup.valid ? undefined : "true"} key={backup.id}><input type="radio" checked={selected === backup.id} onChange={() => setSelected(backup.id)} disabled={!backup.valid || busy} /><span><strong>{backup.filename}</strong><small>{formatDateTime(backup.created_at)} · {formatBytes(backup.size_bytes)} · {backup.valid ? "Hợp lệ" : backup.error}</small><small>Dữ liệu báo cáo: {countsText(backup.counts.business)}</small><small>Tài khoản trong bản sao lưu: {countsText(backup.counts.auth)}</small></span></label>)}{!backups.length ? <p className={`empty`}>Chưa có bản sao lưu. Hệ thống sẽ tự tạo trước lần xóa dữ liệu đầu tiên.</p> : null}</div>
          <button className={`danger-button ${styles.dangerButton}`} type="button" onClick={() => setAsking("restore")} disabled={busy || !selectedBackup?.valid}>Khôi phục bản sao lưu</button>
        </div>
      </section>
      <section className={`section ${styles.section} danger-zone ${styles.dangerZone} panel`}>
        <div className={`section-heading ${styles.sectionHeading}`}><div><p className={`section-label ${styles.sectionLabel} danger-label ${styles.dangerLabel}`}>Bước 2 · Thao tác nguy hiểm</p><h2>Xóa lịch sử báo cáo</h2><p>Tài khoản, mục tiêu và cấu hình đăng nhập vẫn được giữ lại.</p></div></div>
        <div className={`reset-form ${styles.resetForm}`}>
          <p className={`hint ${styles.hint}`}>Chỉ dùng khi cần làm sạch dữ liệu đơn hàng và lịch sử nhập. Hệ thống sẽ tạo và kiểm tra bản sao lưu trước khi xóa.</p>
          <button className={`danger-button ${styles.dangerButton}`} type="button" onClick={() => setAsking("reset")} disabled={busy}>Xóa dữ liệu báo cáo</button>
          {message ? <p className={`reset-result ${styles.resetResult}`} role="status">{message}</p> : null}
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
        {selectedBackup ? <p className={`hint ${styles.hint}`}>{formatDateTime(selectedBackup.created_at)} · {formatBytes(selectedBackup.size_bytes)} · {countsText(selectedBackup.counts.business)}</p> : null}
      </ConfirmDialog>
    </div>
  );
}
