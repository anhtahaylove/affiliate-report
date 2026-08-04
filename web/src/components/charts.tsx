"use client";

import { DailyRow } from "@/lib/api";
import { formatMoney, integer, percent } from "@/lib/format";

export function BarChart({ title, description, rows }: { title: string; description: string; rows: DailyRow[] }) {
  const values = rows.map((row) => Number(row.actual_commission || 0));
  const max = Math.max(1, ...values);
  return (
    <section className="section panel wide chart-panel" aria-labelledby="daily-chart-title" aria-describedby="daily-chart-desc">
      <div className="section-heading">
        <div>
          <p className="section-label">Biểu đồ native</p>
          <h2 id="daily-chart-title">{title}</h2>
          <p id="daily-chart-desc">{description}</p>
        </div>
      </div>
      <div className="bar-chart" role="img" aria-label={`${title}. ${description}`}>
        {rows.map((row) => (
          <div className="bar-column" key={`${row.day}-${row.account}`}>
            <span className="bar" style={{ height: `${Math.max(4, (Number(row.actual_commission || 0) / max) * 100)}%` }} title={`${row.day}: ${formatMoney(row.actual_commission)}`} />
            <small>{row.day.slice(5)}</small>
          </div>
        ))}
      </div>
      <div className="table-wrap chart-fallback" role="region" aria-label={`${title}, có thể cuộn ngang`} tabIndex={0}>
        <table>
          <caption className="sr-only">Dữ liệu thay thế cho biểu đồ hoa hồng theo ngày</caption>
          <thead><tr><th>Ngày</th><th>Đơn</th><th>Hoa hồng</th><th>Đạt KPI</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={`${row.day}-${row.account}-fallback`}><td>{row.day}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_commission)}</td><td>{percent(row.target_achievement)}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}
