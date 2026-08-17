"use client";

import { ImportHistoryRow } from "@/lib/api";
import { FileClock, RotateCcw } from "lucide-react";
import { formatDateTime, integer } from "@/lib/format";
import { AccountIdentity } from "@/components/account-identity";
import type { AccountDirectory } from "@/lib/account-directory";
import styles from "@/components/pages/imports.module.css";

export function RecentImports({ rows, directory, onUndo }: { rows: ImportHistoryRow[]; directory: AccountDirectory; onUndo?: (row: ImportHistoryRow) => void }) {
  return (
    <section className={styles.historyPanel} id="recent-imports" aria-labelledby="recent-imports-title">
      <div className={styles.sectionHeading}>
        <div><p className="section-label">Lịch sử nhập dữ liệu</p><h2 id="recent-imports-title">Các lần nhập gần đây</h2></div>
        <span className={styles.historyCount}>{integer.format(rows.length)} lần</span>
      </div>
      <div className={styles.historyList}>
        {rows.length ? rows.map((item) => (
          <article className={`${styles.historyItem} import-item`} key={item.id}>
            <div className={styles.historyIcon}><FileClock size={18} aria-hidden="true" /></div>
            <div className={styles.historyBody}>
              <div className={styles.historyTitle}>
                <strong title={item.filename}>{item.filename}</strong>
                <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
              </div>
              <div className={`${styles.importAccountSummary} import-account-summary`}><AccountIdentity directory={directory} code={item.account} /></div>
              <dl className={styles.historyMetrics}>
                <div data-tone="success"><dt>Thêm</dt><dd>{integer.format(item.inserted)}</dd></div>
                <div><dt>Cập nhật</dt><dd>{integer.format(item.updated)}</dd></div>
                <div><dt>Trùng</dt><dd>{integer.format(item.unchanged)}</dd></div>
                <div data-tone={item.rejected ? "danger" : undefined}><dt>Lỗi</dt><dd>{integer.format(item.rejected)}</dd></div>
              </dl>
            </div>
            {onUndo ? <button type="button" className={styles.undoButton} onClick={() => onUndo(item)}><RotateCcw size={16} aria-hidden="true" /> Hoàn tác lần nhập này</button> : null}
          </article>
        )) : <div className={styles.historyEmpty}><FileClock size={22} aria-hidden="true" /><p>Chưa có lịch sử. Hãy nhập tệp TikTok đầu tiên để bắt đầu.</p></div>}
      </div>
    </section>
  );
}
