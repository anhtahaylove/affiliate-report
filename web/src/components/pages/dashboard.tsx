"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronDown, Eye, EyeOff, SlidersHorizontal } from "lucide-react";
import {
  AnalyticsResponse,
  CurrentUser,
  ImportHistoryRow,
  MonthlyKpiRow,
  OverviewRow,
  TargetRow,
  loadAnalytics,
  loadDashboard,
  loadImportHistory,
  loadMonthlyKpi,
  loadTargets,
  queryString,
  type DashboardWidget,
  type UiPreferences,
} from "@/lib/api";
import { UrlFilters } from "@/components/filters";
import { canWrite, isOwner, Notice, Skeleton } from "@/components/ui";
import { RecentImports } from "@/components/recent-imports";
import { AccountIdentity } from "@/components/account-identity";
import { useApi } from "@/lib/use-api";
import { achievementTone, currentMonth, formatDateTime, formatMoney, integer, percent } from "@/lib/format";
import type { AccountDirectory } from "@/lib/account-directory";

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
  targets: TargetRow[];
};

type ActionAlert = {
  tone: "success" | "warning" | "danger" | "info";
  title: string;
  copy: string;
  href: string;
  action: string;
};

export function DashboardHome({ user, filters, accounts, directory, preferences, onPreferencesChange }: { user: CurrentUser; filters: UrlFilters; accounts: string[]; directory: AccountDirectory; preferences: UiPreferences; onPreferencesChange: (changes: Partial<Pick<UiPreferences, "dashboard_layout">>) => Promise<void> }) {
  const scope = { accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end };
  const onboardingMonth = currentMonth();
  const { data, error, loading } = useApi<DashboardData>(
    `dashboard-v2:${JSON.stringify([filters.accounts, filters.statuses, filters.start, filters.end, onboardingMonth])}`,
    async () => {
      const [dashboard, monthly, analytics, imports, targets] = await Promise.all([
        loadDashboard(scope),
        loadMonthlyKpi(scope),
        loadAnalytics(scope),
        loadImportHistory(5, filters.accounts),
        loadTargets(onboardingMonth, filters.accounts.length ? filters.accounts : undefined),
      ]);
      return { overview: dashboard.overview, kpi: monthly.items, analytics, history: imports.items, targets: targets.items };
    },
    "Không thể tải trung tâm điều hành.",
  );
  const compactDashboard = useCompactDashboard();

  if (error) return <Notice text={error} />;
  if (loading || !data) return <Skeleton rows={4} tall label="Đang tải trung tâm điều hành" />;

  const { overview, kpi, analytics, history, targets } = data;
  const summary = analytics.summary;
  const previous = analytics.previous_period?.summary;
  const total = filters.accounts.length === 1
    ? overview.find((row) => row.account === filters.accounts[0])
    : overview.find((row) => row.account === "ALL");
  const activeKpi = filters.accounts.length === 1
    ? kpi.find((row) => row.account === filters.accounts[0])
    : kpi.find((row) => row.account === "ALL");
  const selectedLabel = filters.accounts.length ? filters.accounts.map((account) => directory.label(account)).join(" + ") : directory.label("ALL");
  const wholeScope = filters.accounts.length === 0 || filters.accounts.length === accounts.length;
  const setup = { hasAccounts: accounts.length > 0, hasImports: history.length > 0, hasTarget: targets.length > 0 };

  if (wholeScope && (!setup.hasAccounts || !setup.hasImports)) return <FirstRun user={user} setup={setup} />;

  const targetAchievement = analytics.target?.achievement ?? activeKpi?.target_achievement ?? null;
  const progress = Math.max(0, Math.min((targetAchievement ?? 0) * 100, 100));
  const orderDelta = previous ? summary.orders - previous.orders : null;
  const commissionDelta = previous ? summary.actual_commission - previous.actual_commission : null;
  const alerts = buildAlerts(analytics, filters, targetAchievement);
  // "Không có gì để nói" = mọi con số của khối đều bằng 0, chứ không phải thiếu dữ liệu.
  const qualityIssues = analytics.data_quality.unknown_status_rows + analytics.data_quality.non_vnd_rows
    + analytics.data_quality.missing_settlement_date_rows + analytics.data_quality.import_rejected;
  const settlementQuiet = analytics.settlement.pending_lines === 0
    && !(summary.refund_rate ?? 0) && !(summary.ineligible_rate ?? 0);
  const allClear = alerts.length === 1 && alerts[0].tone === "success";
  const layout = preferences.dashboard_layout;
  const widgetStyle = (id: DashboardWidget): CSSProperties => ({ order: layout.order.indexOf(id), display: layout.hidden.includes(id) ? "none" : undefined });

  return (
    <div className="momentum-dashboard">
      {wholeScope && !setup.hasTarget ? <FirstRun user={user} setup={setup} compact /> : null}
      <DashboardCustomizer compact={compactDashboard} preferences={preferences} onPreferencesChange={onPreferencesChange} />
      <section className="today-pulse" style={widgetStyle("today_pulse")} data-widget-id="today_pulse" aria-labelledby="today-pulse-title">
        <div className="pulse-heading">
          <div className="pulse-title-stack">
            <p className="section-label">Tóm tắt hiệu suất</p>
            <h2 id="today-pulse-title">Kết quả trong phạm vi đang xem</h2>
            <div className="pulse-context" aria-label="Phạm vi so sánh">
              <strong>{selectedLabel}</strong>
              <span>So với kỳ trước cùng độ dài</span>
            </div>
          </div>
          <span className="freshness-chip">
            <span className="freshness-dot" aria-hidden="true" />
            <span>Dữ liệu cập nhật</span>
            <strong>{formatDateTime(analytics.data_quality.latest_import_at)}</strong>
          </span>
        </div>
        <div className="pulse-metrics">
          <PulseMetric primary label="Hoa hồng thực tế" value={formatMoney(summary.actual_commission)} delta={commissionDelta == null ? "Chưa có kỳ so sánh" : deltaMoney(commissionDelta)} tone={commissionDelta != null && commissionDelta < 0 ? "danger" : "success"} />
          <PulseMetric label="GMV thực tế" value={formatMoney(summary.actual_gmv ?? total?.actual_gmv)} delta={`Tỷ lệ HH ${percent(summary.effective_commission_rate)}`} />
          <PulseMetric label="Đơn hàng" value={integer.format(summary.orders)} delta={orderDelta == null ? `${integer.format(summary.order_lines)} dòng` : deltaCount(orderDelta)} tone={orderDelta != null && orderDelta < 0 ? "danger" : "success"} />
          <PulseMetric label="Đã nhận cuối cùng" value={formatMoney(summary.final_received)} delta={`Chênh ${formatMoney(summary.final_received_variance)}`} />
        </div>
      </section>

      <section className="momentum-grid target-grid" style={widgetStyle("target_progress")} data-widget-id="target_progress" aria-label="Mục tiêu và dự báo">
        <article className="canvas-panel target-briefing">
          <div className="panel-heading">
            <div><p className="section-label">Mục tiêu và dự báo</p><h2>Khả năng cán đích tháng này</h2></div>
            <Link className="text-action" href="/targets">Điều chỉnh mục tiêu</Link>
          </div>
          <div className="target-briefing-body">
            <div className="target-achievement">
              <ProgressRing value={progress} tone={achievementTone(targetAchievement)} />
              <div className="target-figures">
                <strong>{formatMoney(analytics.target?.actual_commission ?? summary.actual_commission)}</strong>
                <span>trên {formatMoney(analytics.target?.monthly_target ?? activeKpi?.monthly_target)} mục tiêu</span>
                <div className="target-track" role="progressbar" aria-label="Tiến độ mục tiêu" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number(progress.toFixed(1))}><span style={{ width: `${progress}%` }} /></div>
              </div>
            </div>
            <div className="target-pace">
              <p className="section-label">Nhịp cần duy trì</p>
              <dl className="pace-list">
                <PaceRow label="Dự báo cuối tháng" value={formatMoney(analytics.target?.projected_month_end)} />
                <PaceRow label="Còn thiếu" value={formatMoney(analytics.target?.remaining)} tone="warning" />
                <PaceRow label="Cần đạt mỗi ngày" value={formatMoney(analytics.target?.required_per_remaining_day)} />
                <PaceRow label="Ngày còn lại" value={analytics.target ? integer.format(analytics.target.remaining_days) : "—"} />
              </dl>
            </div>
          </div>
        </article>
      </section>

      <section className="canvas-panel action-center" data-quiet={allClear ? "true" : undefined} style={widgetStyle("action_alerts")} data-widget-id="action_alerts" aria-labelledby="action-center-title">
        <div className="panel-heading">
          <div><p className="section-label">Trung tâm hành động</p><h2 id="action-center-title">{allClear ? "Không có việc cần xử lý" : "Việc cần xử lý tiếp theo"}</h2></div>
          <span>{allClear ? "Đã kiểm tra" : `${alerts.length} tín hiệu`}</span>
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

      <DashboardDisclosure
        compact={compactDashboard}
        label="Xu hướng hoa hồng"
        hint={`${integer.format(analytics.trend.length)} kỳ trong phạm vi`}
        style={widgetStyle("trend")}
        widgetId="trend"
      >
        <section className="momentum-grid insight-grid single-widget">
          <article className="canvas-panel trend-canvas">
            <div className="panel-heading"><div><p className="section-label">Xu hướng</p><h2>Hoa hồng và tiền đã nhận</h2></div><Link className="text-action" href="/analytics">Phân tích sâu</Link></div>
            {analytics.trend.length ? <CommissionTrendChart rows={analytics.trend} /> : <p className="empty">Chưa có dữ liệu xu hướng trong phạm vi này.</p>}
            <TrendFallback rows={analytics.trend.slice(-7)} />
          </article>
        </section>
      </DashboardDisclosure>
      <DashboardDisclosure
        compact={compactDashboard}
        label="Đóng góp theo tài khoản"
        hint={analytics.account_breakdown.length <= 1 ? `${directory.label(analytics.account_breakdown[0]?.account ?? "ALL")} chiếm toàn bộ` : `${integer.format(analytics.account_breakdown.length)} tài khoản`}
        quiet={analytics.account_breakdown.length <= 1}
        style={widgetStyle("account_contribution")}
        widgetId="account_contribution"
      >
        <section className="momentum-grid insight-grid single-widget">
          <article className="canvas-panel account-canvas">
            <div className="panel-heading"><div><p className="section-label">Cơ cấu tài khoản</p><h2>Đóng góp theo tài khoản</h2></div></div>
            {analytics.account_breakdown.length ? <AccountContributionChart rows={analytics.account_breakdown} directory={directory} /> : <p className="empty">Chưa có dữ liệu tài khoản.</p>}
          </article>
        </section>
      </DashboardDisclosure>

      <DashboardDisclosure
        compact={compactDashboard}
        label="Dòng tiền đối soát"
        hint={settlementQuiet ? `${integer.format(analytics.settlement.settled_lines)} đơn đã quyết toán, không có dòng chờ` : `${integer.format(analytics.settlement.pending_lines)} dòng đang chờ`}
        quiet={settlementQuiet}
        style={widgetStyle("settlement")}
        widgetId="settlement"
      >
        <section className="momentum-grid settlement-grid single-widget">
          <article className="canvas-panel">
            <div className="panel-heading"><div><p className="section-label">Đối soát</p><h2>Dòng tiền đối soát</h2></div><Link className="text-action" href="/analytics">Mở đối soát</Link></div>
            <div className="settlement-metrics">
              <PulseMetric label="Đã quyết toán" value={integer.format(analytics.settlement.settled_lines)} delta={`Trung vị ${analytics.settlement.median_lag_days ?? "—"} ngày`} />
              <PulseMetric label="Đang chờ" value={integer.format(analytics.settlement.pending_lines)} delta={agingLabel(analytics.settlement.pending_aging)} tone={analytics.settlement.pending_lines ? "warning" : "success"} />
              <PulseMetric label="Hoàn/không hợp lệ" value={percent((summary.refund_rate ?? 0) + (summary.ineligible_rate ?? 0))} delta={`Mất ${formatMoney(activeKpi?.ineligible_commission)}`} tone="danger" />
            </div>
          </article>
        </section>
      </DashboardDisclosure>
      <DashboardDisclosure
        compact={compactDashboard}
        label="Độ tin cậy dữ liệu"
        hint={qualitySummary(analytics)}
        quiet={qualityIssues === 0}
        style={widgetStyle("data_freshness")}
        widgetId="data_freshness"
      >
        <section className="momentum-grid settlement-grid single-widget">
          <article className="canvas-panel freshness-canvas">
            <div className="panel-heading"><div><p className="section-label">Sức khỏe dữ liệu</p><h2>Độ tin cậy dữ liệu</h2></div><Link className="text-action" href="/imports">Kiểm tra import</Link></div>
            <QualityList analytics={analytics} filters={filters} />
          </article>
        </section>
      </DashboardDisclosure>

      <DashboardDisclosure compact={compactDashboard} label="Lần nhập gần đây" hint={`${integer.format(history.length)} lần gần nhất`} style={widgetStyle("recent_imports")} widgetId="recent_imports">
        <RecentImports rows={history} directory={directory} />
      </DashboardDisclosure>
      <div className="dashboard-fixed-footer">
        <DashboardDisclosure compact={compactDashboard} label="Hiệu suất chi tiết" hint={`${integer.format(overview.filter((row) => row.account !== "ALL").length)} tài khoản`}>
          <AccountComparison rows={overview.filter((row) => row.account !== "ALL")} kpi={kpi} directory={directory} />
        </DashboardDisclosure>
      </div>
    </div>
  );
}

const WIDGET_LABELS: Record<DashboardWidget, string> = {
  today_pulse: "Tóm tắt hiệu suất",
  target_progress: "Mục tiêu và dự báo",
  action_alerts: "Trung tâm hành động",
  trend: "Xu hướng hoa hồng",
  account_contribution: "Đóng góp tài khoản",
  settlement: "Đối soát dòng tiền",
  data_freshness: "Độ tin cậy dữ liệu",
  recent_imports: "Lần nhập gần đây",
};

function DashboardCustomizer({ compact, preferences, onPreferencesChange }: { compact: boolean; preferences: UiPreferences; onPreferencesChange: (changes: Partial<Pick<UiPreferences, "dashboard_layout">>) => Promise<void> }) {
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
    <details className="dashboard-customizer panel" style={compact ? { order: 98 } : undefined}>
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

function useCompactDashboard() {
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const sync = () => setCompact(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return compact;
}

/**
 * Thu gọn theo hai lý do độc lập: màn hình hẹp (`compact`), và khối không có gì để nói
 * (`quiet`). Lý do thứ hai dùng lại đúng giao diện tóm tắt đã có cho mobile, nên khối không
 * đổi chỗ và không sinh thêm ngôn ngữ thị giác — chỉ thôi chiếm nguyên một thẻ để nói rằng
 * mọi thứ đều bằng 0. Bấm vào là mở ra như cũ.
 */
function DashboardDisclosure({
  children,
  compact,
  hint,
  label,
  quiet = false,
  style,
  widgetId,
}: {
  children: ReactNode;
  compact: boolean;
  hint: string;
  label: string;
  quiet?: boolean;
  style?: CSSProperties;
  widgetId?: DashboardWidget;
}) {
  const [expanded, setExpanded] = useState(false);
  const collapsible = compact || quiet;
  const open = !collapsible || expanded;

  return (
    <details
      className="mobile-dashboard-disclosure"
      data-widget-id={widgetId}
      data-quiet={quiet && !compact ? "true" : undefined}
      open={open}
      style={style}
      onToggle={(event) => {
        if (collapsible) setExpanded(event.currentTarget.open);
      }}
    >
      <summary className="mobile-dashboard-summary" hidden={!collapsible}>
        <span><strong>{label}</strong><small>{hint}</small></span>
        <ChevronDown className="mobile-dashboard-chevron" size={18} aria-hidden="true" />
      </summary>
      <div className="mobile-dashboard-content">{children}</div>
    </details>
  );
}

function PulseMetric({ label, value, delta, tone = "neutral", primary = false }: { label: string; value: string; delta: string; tone?: "neutral" | "success" | "warning" | "danger"; primary?: boolean }) {
  return <article className="pulse-metric" data-tone={tone} data-primary={primary ? "true" : undefined}><span>{label}</span><strong>{value}</strong><small><span className="metric-signal" aria-hidden="true" />{delta}</small></article>;
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

/**
 * Hai ngữ cảnh khác hẳn nhau dùng chung component này:
 *  - `compact=false`: thật sự lần đầu, chưa có account hoặc chưa nhập gì. Checklist ba bước là
 *    toàn bộ nội dung trang, xứng đáng chiếm chỗ.
 *  - `compact=true`: đã chạy được rồi, chỉ còn sót một bước. Trước đây vẫn dựng nguyên checklist
 *    ba bước giữa dashboard, trong đó hai bước chỉ để khoe dấu "Hoàn tất" — 290px để nói một câu.
 *    Giờ còn một dòng nhắc đúng việc chưa xong.
 */
function FirstRun({ user, setup, compact = false }: { user: CurrentUser; setup: { hasAccounts: boolean; hasImports: boolean; hasTarget: boolean }; compact?: boolean }) {
  const owner = isOwner(user);
  const writer = canWrite(user);
  if (!setup.hasAccounts && !owner) {
    return <section className="canvas-panel first-run" aria-labelledby="first-run-title"><div className="panel-heading"><div><p className="section-label">Chưa có phạm vi dữ liệu</p><h2 id="first-run-title">Liên hệ chủ sở hữu để được cấp account</h2><p>{writer ? "Sau khi được cấp account, bạn có thể nhập tệp và đặt mục tiêu trong phạm vi được phép." : "Tài khoản của bạn đang ở chế độ chỉ xem và chưa được cấp phạm vi báo cáo."}</p></div></div><p className="first-run-guidance">Không có thao tác quản trị nào được mở cho vai trò hiện tại.</p></section>;
  }
  const steps = [
    { done: setup.hasAccounts, href: owner ? "/accounts" : null, title: "Tạo account TikTok", copy: setup.hasAccounts ? "Đã có phạm vi account để vận hành." : "Tạo phạm vi báo cáo cho từng account affiliate." },
    { done: setup.hasImports, href: writer && setup.hasAccounts ? "/imports" : null, title: "Nhập tệp Excel đầu tiên", copy: setup.hasImports ? "Đã có lịch sử import để dựng báo cáo." : "Chọn account, xem hàng đợi rồi nhập tệp TikTok." },
    { done: setup.hasTarget, href: writer && setup.hasAccounts ? "/targets" : null, title: "Đặt mục tiêu tháng", copy: setup.hasTarget ? "Đã có mục tiêu cho tháng hiện tại." : "Mở planner để hệ thống tính pace và dự báo." },
  ];
  const pending = steps.filter((step) => !step.done);
  if (compact && pending.length) {
    const next = pending[0];
    return (
      <section className="canvas-panel first-run is-compact" aria-labelledby="first-run-title">
        <span className="step-index" aria-hidden="true">{steps.length - pending.length + 1}</span>
        <div>
          <strong id="first-run-title">{next.title}</strong>
          <p>{next.copy}</p>
        </div>
        {next.href ? <Link className="text-action" href={next.href}>Mở ngay</Link> : <span className="step-state">Chưa khả dụng</span>}
      </section>
    );
  }
  return <section className="canvas-panel first-run" aria-labelledby="first-run-title"><div className="panel-heading"><div><p className="section-label">Khởi động có hướng dẫn</p><h2 id="first-run-title">Hoàn tất thiết lập vận hành</h2><p>Các bước được cập nhật tự động từ dữ liệu và quyền hiện tại.</p></div></div><ol className="first-run-steps">{steps.map((step, index) => <li key={step.title} data-state={step.done ? "done" : step.href ? "current" : "blocked"}><span className="step-index" aria-hidden="true">{step.done ? "✓" : index + 1}</span><div>{step.href ? <Link href={step.href}><strong>{step.title}</strong></Link> : <strong>{step.title}</strong>}<p>{step.copy}</p></div><span className="step-state">{step.done ? "Hoàn tất" : step.href ? "Cần làm" : "Chưa khả dụng"}</span></li>)}</ol></section>;
}

function AccountComparison({ rows, kpi, directory }: { rows: OverviewRow[]; kpi: MonthlyKpiRow[]; directory: AccountDirectory }) {
  const kpiMap = new Map(kpi.map((row) => [row.account, row]));
  return (
    <section className="canvas-panel account-comparison" id="accounts">
      <div className="panel-heading"><div><p className="section-label">Hiệu suất tài khoản</p><h2>Hiệu suất chi tiết</h2></div><Link className="text-action" href="/accounts">Quản lý tài khoản</Link></div>
      {rows.length ? <>
        <div className="table-wrap desktop-data-table" role="region" aria-label="Bảng hiệu suất tài khoản" tabIndex={0}><table><thead><tr><th>Tài khoản</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Mục tiêu</th><th>Đã đạt</th></tr></thead><tbody>{rows.map((row) => { const achievement = kpiMap.get(row.account)?.target_achievement; return <tr key={row.account}><td><AccountIdentity directory={directory} code={row.account} /></td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(kpiMap.get(row.account)?.monthly_target)}</td><td><span className="tone-text" data-tone={achievementTone(achievement)}>{percent(achievement)}</span></td></tr>; })}</tbody></table></div>
        <div className="mobile-data-list">{rows.map((row) => <article className="mobile-data-card" key={row.account}><div><AccountIdentity directory={directory} code={row.account} /><span>{integer.format(row.orders)} đơn</span></div><dl><div><dt>GMV thực tế</dt><dd>{formatMoney(row.actual_gmv)}</dd></div><div><dt>Hoa hồng</dt><dd>{formatMoney(row.actual_commission)}</dd></div><div><dt>Đạt mục tiêu</dt><dd>{percent(kpiMap.get(row.account)?.target_achievement)}</dd></div></dl></article>)}</div>
      </> : <p className="empty">Chưa có dữ liệu tài khoản trong bộ lọc.</p>}
    </section>
  );
}

function deltaMoney(value: number) { return `${value >= 0 ? "+" : "−"}${formatMoney(Math.abs(value))} so kỳ trước`; }
function deltaCount(value: number) { return `${value >= 0 ? "+" : "−"}${integer.format(Math.abs(value))} đơn so kỳ trước`; }
function agingLabel(rows: AnalyticsResponse["settlement"]["pending_aging"]) { return rows.length ? rows.map((row) => `${row.bucket}: ${integer.format(row.count)}`).join(" · ") : "Không có tồn đọng"; }
function qualitySummary(analytics: AnalyticsResponse) {
  const quality = analytics.data_quality;
  const issues = quality.unknown_status_rows + quality.non_vnd_rows + quality.missing_settlement_date_rows + quality.import_rejected;
  return issues ? `${integer.format(issues)} điểm cần kiểm tra` : "Không có cảnh báo";
}
