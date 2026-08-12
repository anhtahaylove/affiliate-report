"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { Tabs } from "radix-ui";
import { AnalyticsBreakdownRow, AnalyticsDimensionRow, AnalyticsResponse, loadAnalytics } from "@/lib/api";
import { UrlFilters } from "@/components/filters";
import { Notice, Skeleton, StateCard, StatusBadge } from "@/components/ui";
import { useApi } from "@/lib/use-api";
import { formatDateTime, formatMoney, integer, percent, statusLabel } from "@/lib/format";
import { AccountIdentity } from "@/components/account-identity";
import type { AccountDirectory } from "@/lib/account-directory";

const CommissionTrendChart = dynamic(
  () => import("@/components/commerce-intelligence-charts").then((module) => module.CommissionTrendChart),
  { ssr: false, loading: () => <div className="chart-loading" aria-label="Đang dựng biểu đồ" /> },
);
const AccountContributionChart = dynamic(
  () => import("@/components/commerce-intelligence-charts").then((module) => module.AccountContributionChart),
  { ssr: false, loading: () => <div className="chart-loading" aria-label="Đang dựng biểu đồ" /> },
);
const StatusMixChart = dynamic(
  () => import("@/components/commerce-intelligence-charts").then((module) => module.StatusMixChart),
  { ssr: false, loading: () => <div className="chart-loading" aria-label="Đang dựng biểu đồ" /> },
);

export function AnalyticsPage({ filters, directory }: { filters: UrlFilters; directory: AccountDirectory }) {
  const { data, error, loading } = useApi<AnalyticsResponse>(
    `analytics-v2:${JSON.stringify([filters.accounts, filters.statuses, filters.start, filters.end])}`,
    () => loadAnalytics({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end }),
    "Không thể tải Commerce Intelligence.",
  );
  if (error) return <Notice text={error} />;
  if (loading) return <Skeleton rows={4} tall label="Đang tải Commerce Intelligence" />;
  if (!data) return <StateCard text="Chưa có dữ liệu phân tích." />;

  const previous = data.previous_period?.summary;
  const commissionDelta = previous ? data.summary.actual_commission - previous.actual_commission : null;
  const qualityIssues = data.data_quality.unknown_status_rows
    + data.data_quality.non_vnd_rows
    + data.data_quality.missing_settlement_date_rows
    + data.data_quality.import_rejected;

  return (
    <div className="intelligence-page">
      <section className="analytics-pulse" aria-label="Tóm tắt phân tích">
        <InsightMetric label="Hoa hồng thực tế" value={formatMoney(data.summary.actual_commission)} note={commissionDelta == null ? "Chưa có kỳ so sánh" : `${commissionDelta >= 0 ? "+" : "−"}${formatMoney(Math.abs(commissionDelta))} so kỳ trước`} tone={commissionDelta != null && commissionDelta < 0 ? "danger" : "success"} />
        <InsightMetric label="Tỷ lệ hoa hồng" value={percent(data.summary.effective_commission_rate)} note={`${integer.format(data.summary.orders)} đơn`} />
        <InsightMetric label="Dòng tiền đã nhận" value={formatMoney(data.summary.final_received)} note={`Chênh ${formatMoney(data.summary.final_received_variance)}`} />
        <InsightMetric label="Chất lượng dữ liệu" value={qualityIssues ? `${integer.format(qualityIssues)} vấn đề` : "Sạch"} note={`Cập nhật ${formatDateTime(data.data_quality.latest_import_at)}`} tone={qualityIssues ? "warning" : "success"} />
      </section>

      <Tabs.Root className="analytics-tabs" defaultValue="finance">
        <Tabs.List className="analytics-tab-list" aria-label="Nhóm phân tích">
          <Tabs.Trigger value="finance">Tài chính</Tabs.Trigger>
          <Tabs.Trigger value="accounts">Tài khoản</Tabs.Trigger>
          <Tabs.Trigger value="commerce">Sản phẩm & nội dung</Tabs.Trigger>
          <Tabs.Trigger value="settlement">Đối soát</Tabs.Trigger>
          <Tabs.Trigger value="quality">Chất lượng dữ liệu</Tabs.Trigger>
        </Tabs.List>

        <Tabs.Content value="finance" className="analytics-tab-panel">
          <section className="canvas-panel analytics-chart-panel">
            <div className="panel-heading"><div><p className="section-label">Đà tài chính</p><h2>Hoa hồng và dòng tiền theo kỳ</h2></div><span>{data.filters.group_by === "day" ? "Theo ngày" : data.filters.group_by === "week" ? "Theo tuần" : "Theo tháng"}</span></div>
            {data.trend.length ? <CommissionTrendChart rows={data.trend} /> : <p className="empty">Chưa có dữ liệu xu hướng.</p>}
            <ChartDataTable rows={data.trend} />
          </section>
          <div className="analytics-split">
            <section className="canvas-panel">
              <div className="panel-heading"><div><p className="section-label">Phễu đơn hàng</p><h2>Quy mô theo trạng thái</h2></div></div>
              {data.status_breakdown.length ? <StatusMixChart rows={data.status_breakdown} /> : <p className="empty">Chưa có dữ liệu trạng thái.</p>}
            </section>
            <BreakdownList rows={data.status_breakdown} mode="status" />
          </div>
        </Tabs.Content>

        <Tabs.Content value="accounts" className="analytics-tab-panel">
          <div className="analytics-split account-analysis">
            <section className="canvas-panel">
              <div className="panel-heading"><div><p className="section-label">Đóng góp</p><h2>Tài khoản tạo ra hoa hồng</h2></div><Link className="text-action" href="/accounts">Quản lý tài khoản</Link></div>
              {data.account_breakdown.length ? <AccountContributionChart rows={data.account_breakdown} directory={directory} /> : <p className="empty">Chưa có dữ liệu tài khoản.</p>}
            </section>
            <BreakdownList rows={data.account_breakdown} mode="account" directory={directory} />
          </div>
          <BreakdownTable rows={data.account_breakdown} mode="account" directory={directory} />
        </Tabs.Content>

        <Tabs.Content value="commerce" className="analytics-tab-panel">
          <DimensionLeaderboard title="Sản phẩm dẫn đầu" eyebrow="Product momentum" rows={data.products} />
          <DimensionLeaderboard title="Cửa hàng tạo doanh thu" eyebrow="Shop contribution" rows={data.shops} />
          <DimensionLeaderboard title="Nội dung chuyển đổi" eyebrow="Content performance" rows={data.content} />
        </Tabs.Content>

        <Tabs.Content value="settlement" className="analytics-tab-panel">
          <SettlementStudio data={data} />
        </Tabs.Content>

        <Tabs.Content value="quality" className="analytics-tab-panel">
          <QualityStudio data={data} />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

function InsightMetric({ label, value, note, tone = "neutral" }: { label: string; value: string; note: string; tone?: "neutral" | "success" | "warning" | "danger" }) {
  return <article className="insight-metric" data-tone={tone}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function BreakdownList({ rows, mode, directory }: { rows: AnalyticsBreakdownRow[]; mode: "status" | "account"; directory?: AccountDirectory }) {
  return (
    <section className="canvas-panel breakdown-list-panel">
      <div className="panel-heading"><div><p className="section-label">Phân bổ</p><h2>{mode === "status" ? "Tín hiệu cần chú ý" : "Tỷ trọng tài khoản"}</h2></div></div>
      <ol className="rank-list">
        {rows.slice(0, 6).map((row, index) => {
          const label = mode === "status" ? statusLabel(row.status) : directory?.label(row.account) ?? row.account ?? "Chưa xác định";
          const share = row.commission_share ?? 0;
          return <li key={`${mode}-${label}`}><span className="rank-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{label}</strong><small>{integer.format(row.orders)} đơn · {formatMoney(mode === "status" ? row.initial_commission : row.actual_commission)}</small><div className="share-track" aria-label={`${label}: ${percent(share)}`}><span style={{ width: `${Math.max(0, Math.min(share * 100, 100))}%` }} /></div></div><b>{percent(share)}</b></li>;
        })}
      </ol>
    </section>
  );
}

function BreakdownTable({ rows, mode, directory }: { rows: AnalyticsBreakdownRow[]; mode: "status" | "account"; directory?: AccountDirectory }) {
  return <section className="canvas-panel desktop-data-table"><div className="panel-heading"><div><p className="section-label">Chi tiết</p><h2>Bảng đóng góp</h2></div></div><div className="table-wrap" role="region" aria-label="Bảng đóng góp theo tài khoản" tabIndex={0}><table><thead><tr><th>{mode === "status" ? "Trạng thái" : "Tài khoản"}</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Tỷ trọng</th></tr></thead><tbody>{rows.map((row) => <tr key={row[mode === "status" ? "status" : "account"] ?? "unknown"}><td>{mode === "status" ? <StatusBadge status={row.status} /> : directory ? <AccountIdentity directory={directory} code={row.account} /> : row.account}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{percent(row.commission_share)}</td></tr>)}</tbody></table></div></section>;
}

function DimensionLeaderboard({ title, eyebrow, rows }: { title: string; eyebrow: string; rows: AnalyticsDimensionRow[] }) {
  return (
    <section className="canvas-panel dimension-leaderboard">
      <div className="panel-heading"><div><p className="section-label">{eyebrow}</p><h2>{title}</h2></div><span>Top {rows.length}</span></div>
      {rows.length ? <>
        <ol className="dimension-ranks">{rows.slice(0, 5).map((row, index) => <li key={row.id}><span className="rank-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{row.label}</strong><small>{integer.format(row.orders)} đơn · {integer.format(row.units_sold)} sản phẩm</small></div><div><b>{formatMoney(row.actual_commission)}</b><small>Huỷ {percent(row.cancellation_rate)}</small></div></li>)}</ol>
        <div className="table-wrap desktop-data-table" role="region" aria-label={`Bảng ${title.toLowerCase()}`} tabIndex={0}><table><thead><tr><th>Tên</th><th>Đơn</th><th>SL</th><th>Hoàn</th><th>GMV</th><th>Hoa hồng</th><th>Tỷ lệ huỷ</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.label}</td><td>{integer.format(row.orders)}</td><td>{integer.format(row.units_sold)}</td><td>{integer.format(row.units_refunded)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{percent(row.cancellation_rate)}</td></tr>)}</tbody></table></div>
      </> : <p className="empty">Chưa có dữ liệu trong phạm vi này.</p>}
    </section>
  );
}

function SettlementStudio({ data }: { data: AnalyticsResponse }) {
  return (
    <div className="settlement-studio">
      <section className="settlement-hero canvas-panel">
        <div><p className="section-label">Receivables</p><h2>{formatMoney(data.summary.final_received)}</h2><p>Tiền đã nhận cuối cùng trong phạm vi đang xem.</p></div>
        <div className="settlement-kpis"><InsightMetric label="Đã quyết toán" value={integer.format(data.settlement.settled_lines)} note={`Trung vị ${data.settlement.median_lag_days ?? "—"} ngày`} /><InsightMetric label="Đang chờ" value={integer.format(data.settlement.pending_lines)} note="Theo dõi các bucket bên dưới" tone={data.settlement.pending_lines ? "warning" : "success"} /><InsightMetric label="Chênh tiền về" value={formatMoney(data.summary.final_received_variance)} note="So với hoa hồng thực tế" tone={data.summary.final_received_variance < 0 ? "danger" : "neutral"} /></div>
      </section>
      <section className="canvas-panel"><div className="panel-heading"><div><p className="section-label">Pending aging</p><h2>Tuổi khoản đang chờ</h2></div></div>{data.settlement.pending_aging.length ? <div className="aging-grid">{data.settlement.pending_aging.map((row) => <article key={row.bucket}><span>{row.bucket}</span><strong>{integer.format(row.count)}</strong><small>dòng đang chờ</small></article>)}</div> : <p className="empty">Không có khoản đang chờ trong phạm vi này.</p>}</section>
    </div>
  );
}

function QualityStudio({ data }: { data: AnalyticsResponse }) {
  const quality = data.data_quality;
  const issues = [
    ["Trạng thái chưa xác định", quality.unknown_status_rows, "Cần cập nhật mapping trạng thái."],
    ["Không phải VND", quality.non_vnd_rows, "Tách riêng trước khi cộng báo cáo VND."],
    ["Thiếu ngày đơn", quality.missing_order_date_rows, "Không thể xếp đúng kỳ báo cáo."],
    ["Thiếu ngày quyết toán", quality.missing_settlement_date_rows, "Không thể tính độ trễ quyết toán."],
    ["Đã quyết toán nhưng thiếu ngày", quality.settled_missing_settlement_rows, "Dữ liệu trạng thái và ngày không nhất quán."],
    ["Độ trễ quyết toán âm", quality.negative_settlement_lag_rows, "Ngày quyết toán trước ngày đặt đơn."],
    ["Import bị từ chối", quality.import_rejected, "Dòng chưa được đưa vào báo cáo."],
  ] as const;
  return (
    <div className="quality-studio">
      <section className="canvas-panel quality-summary"><div className="panel-heading"><div><p className="section-label">Data lineage</p><h2>Lịch sử xử lý dữ liệu</h2></div><span>Cập nhật {formatDateTime(quality.latest_import_at)}</span></div><div className="quality-flow"><InsightMetric label="Lượt import" value={integer.format(quality.import_batches)} note="batch nguồn bất biến" /><InsightMetric label="Dòng mới" value={integer.format(quality.import_inserted)} note="được thêm vào lịch sử" tone="success" /><InsightMetric label="Đã cập nhật" value={integer.format(quality.import_updated)} note="snapshot mới hơn" /><InsightMetric label="Không thay đổi" value={integer.format(quality.import_unchanged)} note="đã chống trùng" /></div></section>
      <section className="canvas-panel"><div className="panel-heading"><div><p className="section-label">Exceptions</p><h2>Vấn đề cần làm sạch</h2></div><Link className="text-action" href="/imports">Mở lịch sử import</Link></div><div className="exception-list">{issues.map(([label, value, help]) => <article data-tone={value ? "warning" : "success"} key={label}><div><strong>{label}</strong><p>{help}</p></div><span>{integer.format(value)}</span></article>)}</div></section>
    </div>
  );
}

function ChartDataTable({ rows }: { rows: AnalyticsResponse["trend"] }) {
  return <details className="chart-data-disclosure"><summary>Xem bảng dữ liệu biểu đồ</summary><div className="table-wrap" role="region" aria-label="Bảng dữ liệu xu hướng" tabIndex={0}><table><thead><tr><th>Kỳ</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Đã nhận</th></tr></thead><tbody>{rows.map((row) => <tr key={row.period}><td>{row.period}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(row.final_received)}</td></tr>)}</tbody></table></div></details>;
}
