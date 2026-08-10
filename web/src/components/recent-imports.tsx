"use client";

import { ImportHistoryRow } from "@/lib/api";
import { formatDateTime, integer } from "@/lib/format";

export function RecentImports({ rows, onUndo }: { rows: ImportHistoryRow[]; onUndo?: (row: ImportHistoryRow) => void }) {
  return <section className="section panel" id="recent-imports"><div className="section-heading"><div><p className="section-label">Lịch sử nhập dữ liệu</p><h2>Các lần nhập gần đây</h2></div></div><div className="import-list">{rows.length ? rows.map((item) => <article className="import-item" key={item.id}><strong>{item.filename}</strong><span>{item.account} · thêm {integer.format(item.inserted)} · cập nhật {integer.format(item.updated)} · trùng {integer.format(item.unchanged)} · lỗi {integer.format(item.rejected)}</span><time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>{onUndo ? <div className="row-actions"><button type="button" className="danger-button" onClick={() => onUndo(item)}>Hoàn tác lần nhập này</button></div> : null}</article>) : <p className="empty">Chưa có lịch sử. Hãy nhập file TikTok đầu tiên để bắt đầu.</p>}</div></section>;
}
