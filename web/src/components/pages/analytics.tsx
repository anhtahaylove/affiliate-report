"use client";

import { AnalyticsDimensionRow, AnalyticsResponse, loadAnalytics } from "@/lib/api";
import { UrlFilters } from "@/components/filters";
import { Metric, Notice, Skeleton, StateCard, StatusBadge } from "@/components/ui";
import { useApi } from "@/lib/use-api";
import { accountLabel, formatDateTime, formatMoney, integer, percent } from "@/lib/format";

export function AnalyticsPage({ filters }: { filters: UrlFilters }) {
  const { data, error, loading } = useApi<AnalyticsResponse>(
    `analytics:${JSON.stringify([filters.accounts, filters.statuses, filters.start, filters.end])}`,
    () => loadAnalytics({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end }),
    "Không thể tải phân tích.",
  );
  if (error) return <Notice text={error} />;
  if (loading) return <Skeleton rows={3} tall label="Đang tải phân tích" />;
  if (!data) return <StateCard text="Chưa có dữ liệu phân tích." />;
  const summary = data.summary;
  const previous = data.previous_period?.summary;
  const commissionDelta = previous ? summary.actual_commission - previous.actual_commission : null;
  return (
    <div className="content-grid">
      <section className="hero-grid wide" aria-label="Tóm tắt analytics">
        <Metric title="Hoa hồng so kỳ trước" value={commissionDelta == null ? "—" : formatMoney(commissionDelta)} hint={`${integer.format(summary.orders)} đơn kỳ này · ${previous ? integer.format(previous.orders) : "—"} đơn kỳ trước`} />
        <Metric title="Tỷ lệ hoa hồng hiệu dụng" value={percent(summary.effective_commission_rate)} hint={`Hoàn tiền ${percent(summary.refund_rate)} · không đủ điều kiện ${percent(summary.ineligible_rate)}`} />
        <Metric title="Độ mới dữ liệu" value={formatDateTime(data.data_quality.latest_import_at)} hint={`Đơn mới nhất ${summary.latest_order_date ?? "—"}`} />
      </section>
      <AnalyticsTrend rows={data.trend} />
      <AnalyticsBreakdown title="Theo trạng thái" rows={data.status_breakdown} labelKey="status" />
      <AnalyticsBreakdown title="Theo tài khoản" rows={data.account_breakdown} labelKey="account" />
      <DimensionTable title="Sản phẩm" rows={data.products} />
      <DimensionTable title="Cửa hàng" rows={data.shops} />
      <DimensionTable title="Nội dung" rows={data.content} />
      <SettlementQuality data={data} />
    </div>
  );
}

/** Bar path with rounded top corners and a flat bottom, so the mark stays anchored to the baseline. */
function roundedTopBarPath(x: number, y: number, width: number, height: number, radius: number) {
  const r = Math.max(0, Math.min(radius, width / 2, height));
  return `M${x},${y + height} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${y + height} Z`;
}

/** Rút gọn tiền cho nhãn trục: 1.200.000 → "1,2 tr". Trục chỉ để ước lượng, số chính xác nằm ở bảng. */
function axisLabel(value: number) {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1).replace(".", ",")} tỷ`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(".", ",")} tr`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(value);
}

const CHART = { width: 900, height: 260, left: 74, right: 16, top: 16, bottom: 34 };

function AnalyticsTrend({ rows }: { rows: AnalyticsResponse["trend"] }) {
  const chartRows = rows.slice(-30);
  const max = Math.max(...chartRows.map((row) => row.actual_commission), 1);
  const plotWidth = CHART.width - CHART.left - CHART.right;
  const plotHeight = CHART.height - CHART.top - CHART.bottom;
  const baseline = CHART.top + plotHeight;
  const step = chartRows.length ? plotWidth / chartRows.length : plotWidth;
  const barWidth = Math.max(step * 0.68, 1);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <section className="section panel wide">
      <div className="section-heading"><div><p className="section-label">Xu hướng tài chính</p><h2>Hoa hồng theo kỳ</h2></div></div>
      {rows.length ? (
        <>
          <svg className="analytics-svg" viewBox={`0 0 ${CHART.width} ${CHART.height}`} role="img" aria-labelledby="analytics-trend-title analytics-trend-desc">
            <title id="analytics-trend-title">Hoa hồng thực tế theo kỳ</title>
            <desc id="analytics-trend-desc">Biểu đồ cột của tối đa 30 kỳ gần nhất; bảng ngay sau biểu đồ chứa dữ liệu đầy đủ.</desc>
            {ticks.map((tick) => {
              const y = baseline - tick * plotHeight;
              return (
                <g key={tick}>
                  <line className="analytics-grid" x1={CHART.left} y1={y} x2={CHART.width - CHART.right} y2={y} />
                  <text className="analytics-tick" x={CHART.left - 10} y={y + 4} textAnchor="end">{axisLabel(Math.round(max * tick))}</text>
                </g>
              );
            })}
            <line className="analytics-axis" x1={CHART.left} y1={baseline} x2={CHART.width - CHART.right} y2={baseline} />
            {chartRows.map((row, index) => {
              const height = Math.max((row.actual_commission / max) * plotHeight, 2);
              const x = CHART.left + index * step + (step - barWidth) / 2;
              const last = index === chartRows.length - 1;
              return (
                <g key={row.period} className={last ? "bar last" : "bar"}>
                  <path d={roundedTopBarPath(x, baseline - height, barWidth, height, 3)} />
                  <rect x={CHART.left + index * step} y={CHART.top} width={step} height={plotHeight} className="bar-hit">
                    <title>{`${row.period}: ${formatMoney(row.actual_commission)}`}</title>
                  </rect>
                </g>
              );
            })}
            {chartRows.length ? (
              <>
                <text className="analytics-tick" x={CHART.left} y={CHART.height - 12} textAnchor="start">{chartRows[0].period}</text>
                <text className="analytics-tick" x={CHART.width - CHART.right} y={CHART.height - 12} textAnchor="end">{chartRows[chartRows.length - 1].period}</text>
              </>
            ) : null}
          </svg>
          <div className="table-wrap chart-fallback" role="region" aria-label="Bảng xu hướng hoa hồng, có thể cuộn ngang" tabIndex={0}><table><thead><tr><th>Kỳ</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Đã nhận</th></tr></thead><tbody>{rows.map((row) => <tr key={row.period}><td>{row.period}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(row.final_received)}</td></tr>)}</tbody></table></div>
        </>
      ) : <p className="empty">Chưa có dữ liệu xu hướng trong bộ lọc.</p>}
    </section>
  );
}

function AnalyticsBreakdown({ title, rows, labelKey }: { title: string; rows: AnalyticsResponse["status_breakdown"]; labelKey: "status" | "account" }) {
  // Bảng "Theo trạng thái" nhóm chính theo status, nên với dòng "Không đủ điều kiện" thì
  // actual_gmv/actual_commission luôn = 0 do định nghĩa (bị trừ hết) — hiện số đó ở đây sẽ trông
  // như thiếu dữ liệu. Dùng gross_gmv/initial_commission (số thô, chưa trừ đơn không đủ điều
  // kiện) để mỗi dòng vẫn phản ánh đúng quy mô đơn thật sự có trong file gốc. Bảng "Theo tài
  // khoản" thì giữ actual vì đó là con số thực nhận có ý nghĩa để so sánh giữa các account.
  const byStatus = labelKey === "status";
  return (
    <section className="section panel">
      <div className="section-heading"><div><p className="section-label">Phân bổ</p><h2>{title}</h2></div></div>
      <div className="table-wrap" role="region" aria-label={`${title}, có thể cuộn ngang`} tabIndex={0}>{rows.length ? <table><thead><tr><th>{byStatus ? "Trạng thái" : "Tài khoản"}</th><th>Đơn</th><th>{byStatus ? "GMV" : "GMV thực tế"}</th><th>{byStatus ? "Hoa hồng ước tính" : "Hoa hồng thực tế"}</th><th>Tỷ trọng HH</th></tr></thead><tbody>{rows.map((row) => <tr key={row[labelKey] ?? "unknown"}><td>{byStatus ? <StatusBadge status={row.status} /> : accountLabel(row.account)}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(byStatus ? row.gross_gmv : row.actual_gmv)}</td><td>{formatMoney(byStatus ? row.initial_commission : row.actual_commission)}</td><td>{percent(row.commission_share)}</td></tr>)}</tbody></table> : <p className="empty">Chưa có dữ liệu {title.toLowerCase()}.</p>}</div>
    </section>
  );
}

function DimensionTable({ title, rows }: { title: string; rows: AnalyticsDimensionRow[] }) {
  return (
    <section className="section panel wide">
      <div className="section-heading"><div><p className="section-label">Xếp hạng</p><h2>{title}</h2></div></div>
      <div className="table-wrap" role="region" aria-label={`Xếp hạng ${title.toLowerCase()}, có thể cuộn ngang`} tabIndex={0}>{rows.length ? <table><thead><tr><th>Tên</th><th>Đơn</th><th>SL</th><th>Hoàn</th><th>GMV</th><th>HH</th><th>Tỷ lệ huỷ</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.label}</td><td>{integer.format(row.orders)}</td><td>{integer.format(row.units_sold)}</td><td>{integer.format(row.units_refunded)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{percent(row.cancellation_rate)}</td></tr>)}</tbody></table> : <p className="empty">Chưa có dữ liệu {title.toLowerCase()} trong bộ lọc.</p>}</div>
    </section>
  );
}

function SettlementQuality({ data }: { data: AnalyticsResponse }) {
  const quality = data.data_quality;
  const qualityRows = [
    ["Trạng thái chưa xác định", quality.unknown_status_rows],
    ["Không phải VND", quality.non_vnd_rows],
    ["Thiếu ngày đơn", quality.missing_order_date_rows],
    ["Thiếu ngày quyết toán", quality.missing_settlement_date_rows],
    ["Đã quyết toán nhưng thiếu ngày quyết toán", quality.settled_missing_settlement_rows],
    ["Thời gian quyết toán âm", quality.negative_settlement_lag_rows],
    ["Dòng nhập bị từ chối", quality.import_rejected],
  ];
  return (
    <section className="section panel wide">
      <div className="section-heading"><div><p className="section-label">Quyết toán và chất lượng dữ liệu</p><h2>Đối soát dữ liệu</h2></div></div>
      <div className="content-grid compact-grid">
        <div className="import-item"><strong>Tình trạng quyết toán</strong><span>Đã quyết toán {integer.format(data.settlement.settled_lines)} · Đang chờ {integer.format(data.settlement.pending_lines)} · Trung vị {data.settlement.median_lag_days ?? "—"} ngày</span>{data.settlement.pending_aging.length ? <small>{data.settlement.pending_aging.map((item) => `${item.bucket}: ${integer.format(item.count)}`).join(" · ")}</small> : null}</div>
        <div className="import-item"><strong>Độ mới dữ liệu nhập</strong><span>{formatDateTime(quality.latest_import_at)} · {integer.format(quality.import_batches)} lượt nhập</span><small>Thêm {integer.format(quality.import_inserted)} · cập nhật {integer.format(quality.import_updated)} · trùng {integer.format(quality.import_unchanged)}</small></div>
      </div>
      <div className="table-wrap chart-fallback" role="region" aria-label="Bảng cảnh báo chất lượng dữ liệu" tabIndex={0}><table><thead><tr><th>Cảnh báo</th><th>Số dòng</th></tr></thead><tbody>{qualityRows.map(([label, count]) => <tr key={label}><td>{label}</td><td>{integer.format(count as number)}</td></tr>)}</tbody></table></div>
    </section>
  );
}
