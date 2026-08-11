"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { ArrowDown, ArrowUp, Eye, EyeOff, SlidersHorizontal } from "lucide-react";
import {
  AnalyticsResponse,
  ImportHistoryRow,
  MonthlyKpiRow,
  OverviewRow,
  loadAnalytics,
  loadDashboard,
  loadImportHistory,
  loadMonthlyKpi,
  queryString,
  type DashboardWidget,
  type UiPreferences,
} from "@/lib/api";
import { UrlFilters } from "@/components/filters";
import { Notice, Skeleton } from "@/components/ui";
import { RecentImports } from "@/components/recent-imports";
import { useApi } from "@/lib/use-api";
import { accountLabel, achievementTone, formatDateTime, formatMoney, integer, percent } from "@/lib/format";

const CommissionTrendChart = dynamic(
  () => import("@/components/commerce-intelligence-charts").then((module) => module.CommissionTrendChart),
  { ssr: false, loading: () => <div className="chart-loading" aria-label="Đang dựng biểu đồ" /> },
);
const AccountContributionChart = dynamic(
  () => import("@/components/commerce-intelligence-charts").then((module) => module.AccountContributionChart),
  { ssr: false, loading: () => <div className="chart-loading" aria-label="Đang dựng biểu đồ" /> },
);

type DashboardData = {
  overview: OverviewRow[];
  kpi: MonthlyKpiRow[];
  analytics: AnalyticsResponse;
  history: ImportHistoryRow[];
};

type ActionAlert = {
  tone: "success" | "warning" | "danger" | "info";
  title: string;
  copy: string;
  href: string;
  action: string;
};

export function DashboardHome({ filters, accounts, preferences, onPreferencesChange }: { filters: UrlFilters; accounts: string[]; preferences: UiPreferences; onPreferencesChange: (changes: Partial<Pick<UiPreferences, "dashboard_layout">>) => Promise<void> }) {
  const scope = { accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end };
  const { data, error, loading } = useApi<DashboardData>(
    `dashboard-v2:${JSON.stringify([filters.accounts, filters.statuses, filters.start, filters.end])}`,
    async () => {
      const [dashboard, monthly, analytics, imports] = await Promise.all([
        loadDashboard(scope),
        loadMonthlyKpi(scope),
        loadAnalytics(scope),
        loadImportHistory(5, filters.accounts),
      ]);
      return { overview: dashboard.overview, kpi: monthly.items, analytics, history: imports.items };
    },
    "Không thể tải trung tâm điều hành.",
  );

  if (error) return <Notice text={error} />;
  if (loading || !data) return <Skeleton rows={4} tall label="Đang tải trung tâm điều hành" />;

  const { overview, kpi, analytics, history } = data;
  const summary = analytics.summary;
  const previous = analytics.previous_period?.summary;
  const total = filters.accounts.length === 1
    ? overview.find((row) => row.account === filters.accounts[0])
    : overview.find((row) => row.account === "ALL");
  const activeKpi = filters.accounts.length === 1
    ? kpi.find((row) => row.account === filters.accounts[0])
    : kpi.find((row) => row.account === "ALL");
  const selectedLabel = filters.accounts.length ? filters.accounts.join(" + ") : accountLabel("ALL");
  const wholeScope = filters.accounts.length === 0 || filters.accounts.length === accounts.length;

  if (wholeScope && !history.length && summary.order_lines === 0) return <FirstRun />;

  const targetAchievement = analytics.target?.achievement ?? activeKpi?.target_achievement ?? null;
  const progress = Math.max(0, Math.min((targetAchievement ?? 0) * 100, 100));
  const orderDelta = previous ? summary.orders - previous.orders : null;
  const commissionDelta = previous ? summary.actual_commission - previous.actual_commission : null;
  const alerts = buildAlerts(analytics, filters, targetAchievement);
  const layout = preferences.dashboard_layout;
  const widgetStyle = (id: DashboardWidget) => ({ order: layout.order.indexOf(id), display: layout.hidden.includes(id) ? "none" : undefined });

  return (
    <div className="momentum-dashboard">
      <DashboardCustomizer preferences={preferences} onPreferencesChange={onPreferencesChange} />
      <section className="today-pulse" style={widgetStyle("today_pulse")} data-widget-id="today_pulse" aria-labelledby="today-pulse-title">
        <div className="pulse-heading">
          <div>
            <p className="section-label">Nhịp hôm nay</p>
            <h2 id="today-pulse-title">Nhịp kinh doanh đang diễn ra</h2>
            <p>{selectedLabel} · so với kỳ liền trước trên cùng độ dài thời gian.</p>
          </div>
          <span className="freshness-chip">Cập nhật {formatDateTime(analytics.data_quality.latest_import_at)}</span>
        </div>
        <div className="pulse-metrics">
          <PulseMetric label="Hoa hồng thực tế" value={formatMoney(summary.actual_commission)} delta={commissionDelta == null ? "Chưa có kỳ so sánh" : deltaMoney(commissionDelta)} tone={commissionDelta != null && commissionDelta < 0 ? "danger" : "success"} />
          <PulseMetric label="GMV thực tế" value={formatMoney(summary.actual_gmv ?? total?.actual_gmv)} delta={`Tỷ lệ HH ${percent(summary.effective_commission_rate)}`} />
          <PulseMetric label="Đơn hàng" value={integer.format(summary.orders)} delta={orderDelta == null ? `${integer.format(summary.order_lines)} dòng` : deltaCount(orderDelta)} tone={orderDelta != null && orderDelta < 0 ? "danger" : "success"} />
          <PulseMetric label="Đã nhận cuối cùng" value={formatMoney(summary.final_received)} delta={`Chênh ${formatMoney(summary.final_received_variance)}`} />
        </div>
      </section>

      <section className="momentum-grid target-grid" style={widgetStyle("target_progress")} data-widget-id="target_progress" aria-label="Mục tiêu và dự báo">
        <article className="canvas-panel target-canvas">
          <div className="panel-heading">
            <div><p className="section-label">Tiến độ</p><h2>Mục tiêu tháng</h2></div>
            <Link className="text-action" href="/targets">Điều chỉnh mục tiêu</Link>
          </div>
          <div className="target-body">
            <ProgressRing value={progress} tone={achievementTone(targetAchievement)} />
            <div className="target-figures">
              <strong>{formatMoney(analytics.target?.actual_commission ?? summary.actual_commission)}</strong>
              <span>trên {formatMoney(analytics.target?.monthly_target ?? activeKpi?.monthly_target)} mục tiêu</span>
              <div className="target-track" role="progressbar" aria-label="Tiến độ mục tiêu" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number(progress.toFixed(1))}><span style={{ width: `${progress}%` }} /></div>
            </div>
          </div>
        </article>
        <article className="canvas-panel pace-canvas">
          <div className="panel-heading"><div><p className="section-label">Nhịp mục tiêu</p><h2>Khả năng cán đích</h2></div></div>
          <dl className="pace-list">
            <PaceRow label="Dự báo cuối tháng" value={formatMoney(analytics.target?.projected_month_end)} />
            <PaceRow label="Còn thiếu" value={formatMoney(analytics.target?.remaining)} tone="warning" />
            <PaceRow label="Cần đạt mỗi ngày" value={formatMoney(analytics.target?.required_per_remaining_day)} />
            <PaceRow label="Ngày còn lại" value={analytics.target ? integer.format(analytics.target.remaining_days) : "—"} />
          </dl>
        </article>
      </section>

      <section className="canvas-panel action-center" style={widgetStyle("action_alerts")} data-widget-id="action_alerts" aria-labelledby="action-center-title">
        <div className="panel-heading">
          <div><p className="section-label">Trung tâm hành động</p><h2 id="action-center-title">Việc cần xử lý tiếp theo</h2></div>
          <span>{alerts.length} tín hiệu</span>
        </div>
        <div className="alert-grid">
          {alerts.map((alert) => (
            <article className="action-alert" data-tone={alert.tone} key={alert.title}>
              <span className="alert-signal" aria-hidden="true" />
              <div><strong>{alert.title}</strong><p>{alert.copy}</p></div>
              <Link href={alert.href}>{alert.action}</Link>
            </article>
          ))}
        </div>
      </section>

      <section className="momentum-grid insight-grid" style={widgetStyle("trend")} data-widget-id="trend">
        <article className="canvas-panel trend-canvas">
          <div className="panel-heading"><div><p className="section-label">Xu hướng</p><h2>Hoa hồng và tiền đã nhận</h2></div><Link className="text-action" href="/analytics">Phân tích sâu</Link></div>
          {analytics.trend.length ? <CommissionTrendChart rows={analytics.trend} /> : <p className="empty">Chưa có dữ liệu xu hướng trong phạm vi này.</p>}
          <TrendFallback rows={analytics.trend.slice(-7)} />
        </article>
      </section>
      <section className="momentum-grid insight-grid single-widget" style={widgetStyle("account_contribution")} data-widget-id="account_contribution">
        <article className="canvas-panel account-canvas">
          <div className="panel-heading"><div><p className="section-label">Cơ cấu tài khoản</p><h2>Đóng góp theo tài khoản</h2></div></div>
          {analytics.account_breakdown.length ? <AccountContributionChart rows={analytics.account_breakdown} /> : <p className="empty">Chưa có dữ liệu tài khoản.</p>}
        </article>
      </section>

      <section className="momentum-grid settlement-grid single-widget" style={widgetStyle("settlement")} data-widget-id="settlement">
        <article className="canvas-panel">
          <div className="panel-heading"><div><p className="section-label">Đối soát</p><h2>Dòng tiền đối soát</h2></div><Link className="text-action" href="/analytics">Mở đối soát</Link></div>
          <div className="settlement-metrics">
            <PulseMetric label="Đã quyết toán" value={integer.format(analytics.settlement.settled_lines)} delta={`Trung vị ${analytics.settlement.median_lag_days ?? "—"} ngày`} />
            <PulseMetric label="Đang chờ" value={integer.format(analytics.settlement.pending_lines)} delta={agingLabel(analytics.settlement.pending_aging)} tone={analytics.settlement.pending_lines ? "warning" : "success"} />
            <PulseMetric label="Hoàn/không hợp lệ" value={percent((summary.refund_rate ?? 0) + (summary.ineligible_rate ?? 0))} delta={`Mất ${formatMoney(activeKpi?.ineligible_commission)}`} tone="danger" />
          </div>
        </article>
      </section>
      <section className="momentum-grid settlement-grid single-widget" style={widgetStyle("data_freshness")} data-widget-id="data_freshness">
        <article className="canvas-panel freshness-canvas">
          <div className="panel-heading"><div><p className="section-label">Sức khỏe dữ liệu</p><h2>Độ tin cậy dữ liệu</h2></div><Link className="text-action" href="/imports">Kiểm tra import</Link></div>
          <QualityList analytics={analytics} filters={filters} />
        </article>
      </section>

      <section style={widgetStyle("recent_imports")} data-widget-id="recent_imports"><RecentImports rows={history} /></section>
      <div className="dashboard-fixed-footer"><AccountComparison rows={overview.filter((row) => row.account !== "ALL")} kpi={kpi} /></div>
    </div>
  );
}

const WIDGET_LABELS: Record<DashboardWidget, string> = {
  today_pulse: "Nhịp hôm nay",
  target_progress: "Mục tiêu và dự báo",
  action_alerts: "Trung tâm hành động",
  trend: "Xu hướng hoa hồng",
  account_contribution: "Đóng góp tài khoản",
  settlement: "Đối soát dòng tiền",
  data_freshness: "Độ tin cậy dữ liệu",
  recent_imports: "Lần nhập gần đây",
};

function DashboardCustomizer({ preferences, onPreferencesChange }: { preferences: UiPreferences; onPreferencesChange: (changes: Partial<Pick<UiPreferences, "dashboard_layout">>) => Promise<void> }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const layout = preferences.dashboard_layout;

  async function save(order: DashboardWidget[], hidden: DashboardWidget[]) {
    setSaving(true);
    setError("");
    try {
      await onPreferencesChange({ dashboard_layout: { schema: 1, order, hidden } });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể lưu bố cục dashboard.");
    } finally {
      setSaving(false);
    }
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= layout.order.length) return;
    const order = [...layout.order];
    [order[index], order[target]] = [order[target], order[index]];
    void save(order, layout.hidden);
  }

  function toggle(id: DashboardWidget) {
    const hidden = layout.hidden.includes(id) ? layout.hidden.filter((item) => item !== id) : [...layout.hidden, id];
    void save(layout.order, hidden);
  }

  return (
    <details className="dashboard-customizer panel">
      <summary><span><SlidersHorizontal size={17} aria-hidden="true" /><strong>Tùy chỉnh dashboard</strong></span><small>Ẩn, hiện hoặc đổi thứ tự widget</small></summary>
      <div className="dashboard-widget-list" aria-busy={saving}>
        {layout.order.map((id, index) => (
          <div key={id} className="dashboard-widget-row">
            <span><strong>{WIDGET_LABELS[id]}</strong><small>{layout.hidden.includes(id) ? "Đang ẩn" : `Vị trí ${index + 1}`}</small></span>
            <div className="row-actions">
              <button type="button" disabled={saving || index === 0} onClick={() => move(index, -1)} aria-label={`Đưa ${WIDGET_LABELS[id]} lên`}><ArrowUp size={16} aria-hidden="true" /></button>
              <button type="button" disabled={saving || index === layout.order.length - 1} onClick={() => move(index, 1)} aria-label={`Đưa ${WIDGET_LABELS[id]} xuống`}><ArrowDown size={16} aria-hidden="true" /></button>
              <button type="button" disabled={saving} onClick={() => toggle(id)}>{layout.hidden.includes(id) ? <Eye size={16} aria-hidden="true" /> : <EyeOff size={16} aria-hidden="true" />}{layout.hidden.includes(id) ? "Hiện" : "Ẩn"}</button>
            </div>
          </div>
        ))}
      </div>
      {error ? <p className="filter-error" role="alert">{error}</p> : null}
    </details>
  );
}

function PulseMetric({ label, value, delta, tone = "neutral" }: { label: string; value: string; delta: string; tone?: "neutral" | "success" | "warning" | "danger" }) {
  return <article className="pulse-metric" data-tone={tone}><span>{label}</span><strong>{value}</strong><small>{delta}</small></article>;
}

function PaceRow({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "warning" }) {
  return <div data-tone={tone}><dt>{label}</dt><dd>{value}</dd></div>;
}

function ProgressRing({ value, tone }: { value: number; tone: string }) {
  const radius = 43;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  return (
    <div className="progress-ring" data-tone={tone}>
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle className="ring-track" cx="50" cy="50" r={radius} />
        <circle className="ring-value" cx="50" cy="50" r={radius} strokeDasharray={circumference} strokeDashoffset={offset} />
      </svg>
      <strong>{Math.round(value)}%</strong>
    </div>
  );
}

function buildAlerts(analytics: AnalyticsResponse, filters: UrlFilters, achievement: number | null): ActionAlert[] {
  const alerts: ActionAlert[] = [];
  const quality = analytics.data_quality;
  const target = analytics.target;
  const unknownHref = `/orders${queryString({ month: filters.month, start: filters.start, end: filters.end, account: filters.accounts, status: "unknown" })}`;
  if (target && achievement != null && achievement < target.elapsed_days / Math.max(target.scope_days, 1)) {
    alerts.push({ tone: "warning", title: "Nhịp mục tiêu đang chậm", copy: `Cần ${formatMoney(target.required_per_remaining_day)} mỗi ngày trong ${target.remaining_days} ngày còn lại.`, href: "/targets", action: "Mở planner" });
  }
  if (quality.unknown_status_rows > 0) alerts.push({ tone: "danger", title: "Có trạng thái chưa xác định", copy: `${integer.format(quality.unknown_status_rows)} dòng cần kiểm tra mapping trước khi chốt báo cáo.`, href: unknownHref, action: "Xem đơn" });
  if (quality.import_rejected > 0) alerts.push({ tone: "danger", title: "Import có dòng bị từ chối", copy: `${integer.format(quality.import_rejected)} dòng chưa đi vào báo cáo.`, href: "/imports", action: "Xem kết quả" });
  if (analytics.settlement.pending_lines > 0) alerts.push({ tone: "info", title: "Dòng tiền đang chờ quyết toán", copy: `${integer.format(analytics.settlement.pending_lines)} dòng đang chờ TikTok xác nhận.`, href: "/analytics", action: "Mở đối soát" });
  if (!alerts.length) alerts.push({ tone: "success", title: "Không có cảnh báo ưu tiên", copy: "Dữ liệu hiện tại sạch và nhịp mục tiêu chưa phát sinh rủi ro cần xử lý.", href: "/analytics", action: "Xem phân tích" });
  return alerts.slice(0, 4);
}

function QualityList({ analytics, filters }: { analytics: AnalyticsResponse; filters: UrlFilters }) {
  const quality = analytics.data_quality;
  const unknownHref = `/orders${queryString({ month: filters.month, start: filters.start, end: filters.end, account: filters.accounts, status: "unknown" })}`;
  const rows = [
    { label: "Trạng thái chưa xác định", value: quality.unknown_status_rows, href: unknownHref },
    { label: "Tiền tệ khác VND", value: quality.non_vnd_rows },
    { label: "Thiếu ngày quyết toán", value: quality.missing_settlement_date_rows },
    { label: "Dòng import bị từ chối", value: quality.import_rejected, href: "/imports" },
  ];
  return <ul className="quality-list">{rows.map((row) => <li key={row.label}><span>{row.label}</span>{row.href ? <Link href={row.href}>{integer.format(row.value)}</Link> : <strong>{integer.format(row.value)}</strong>}</li>)}</ul>;
}

function TrendFallback({ rows }: { rows: AnalyticsResponse["trend"] }) {
  return <div className="sr-chart-table"><table><caption>Dữ liệu xu hướng bảy kỳ gần nhất</caption><thead><tr><th>Kỳ</th><th>Hoa hồng</th><th>Đã nhận</th></tr></thead><tbody>{rows.map((row) => <tr key={row.period}><td>{row.period}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(row.final_received)}</td></tr>)}</tbody></table></div>;
}

function FirstRun() {
  const steps = [
    { href: "/accounts", title: "Tạo tài khoản TikTok", copy: "Tạo phạm vi báo cáo cho từng tài khoản affiliate." },
    { href: "/imports", title: "Nhập tệp Excel đầu tiên", copy: "Chọn tài khoản, kiểm tra hàng đợi rồi nhập tệp TikTok." },
    { href: "/targets", title: "Đặt mục tiêu tháng", copy: "Mở planner để hệ thống tính pace và dự báo." },
  ];
  return <section className="canvas-panel first-run"><div className="panel-heading"><div><p className="section-label">Khởi động</p><h2>Thiết lập workspace đầu tiên</h2><p>Hoàn tất ba bước để mở toàn bộ Commerce Intelligence.</p></div></div><ol className="first-run-steps">{steps.map((step, index) => <li key={step.href}><span className="step-index" aria-hidden="true">{index + 1}</span><div><Link href={step.href}><strong>{step.title}</strong></Link><p>{step.copy}</p></div></li>)}</ol></section>;
}

function AccountComparison({ rows, kpi }: { rows: OverviewRow[]; kpi: MonthlyKpiRow[] }) {
  const kpiMap = new Map(kpi.map((row) => [row.account, row]));
  return (
    <section className="canvas-panel account-comparison" id="accounts">
      <div className="panel-heading"><div><p className="section-label">Hiệu suất tài khoản</p><h2>Hiệu suất chi tiết</h2></div><Link className="text-action" href="/accounts">Quản lý tài khoản</Link></div>
      {rows.length ? <>
        <div className="table-wrap desktop-data-table" role="region" aria-label="Bảng hiệu suất tài khoản" tabIndex={0}><table><thead><tr><th>Tài khoản</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Mục tiêu</th><th>Đã đạt</th></tr></thead><tbody>{rows.map((row) => { const achievement = kpiMap.get(row.account)?.target_achievement; return <tr key={row.account}><td>{accountLabel(row.account)}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(kpiMap.get(row.account)?.monthly_target)}</td><td><span className="tone-text" data-tone={achievementTone(achievement)}>{percent(achievement)}</span></td></tr>; })}</tbody></table></div>
        <div className="mobile-data-list">{rows.map((row) => <article className="mobile-data-card" key={row.account}><div><strong>{accountLabel(row.account)}</strong><span>{integer.format(row.orders)} đơn</span></div><dl><div><dt>GMV thực tế</dt><dd>{formatMoney(row.actual_gmv)}</dd></div><div><dt>Hoa hồng</dt><dd>{formatMoney(row.actual_commission)}</dd></div><div><dt>Đạt mục tiêu</dt><dd>{percent(kpiMap.get(row.account)?.target_achievement)}</dd></div></dl></article>)}</div>
      </> : <p className="empty">Chưa có dữ liệu tài khoản trong bộ lọc.</p>}
    </section>
  );
}

function deltaMoney(value: number) { return `${value >= 0 ? "+" : "−"}${formatMoney(Math.abs(value))} so kỳ trước`; }
function deltaCount(value: number) { return `${value >= 0 ? "+" : "−"}${integer.format(Math.abs(value))} đơn so kỳ trước`; }
function agingLabel(rows: AnalyticsResponse["settlement"]["pending_aging"]) { return rows.length ? rows.map((row) => `${row.bucket}: ${integer.format(row.count)}`).join(" · ") : "Không có tồn đọng"; }
