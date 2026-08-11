"use client";

import Link from "next/link";
import { DailyRow, ImportHistoryRow, MonthlyKpiRow, OverviewRow, loadAnalytics, loadDashboard, loadImportHistory, loadMonthlyKpi, queryString } from "@/lib/api";
import { AnalyticsResponse } from "@/lib/api";
import { BarChart } from "@/components/charts";
import { UrlFilters } from "@/components/filters";
import { Metric, Notice, Skeleton } from "@/components/ui";
import { RecentImports } from "@/components/recent-imports";
import { useApi } from "@/lib/use-api";
import { accountLabel, achievementTone, formatDateTime, formatMoney, integer, percent } from "@/lib/format";

type DashboardData = {
  overview: OverviewRow[];
  daily: DailyRow[];
  kpi: MonthlyKpiRow[];
  analytics: AnalyticsResponse;
  history: ImportHistoryRow[];
};

export function DashboardHome({ filters, accounts }: { filters: UrlFilters; accounts: string[] }) {
  const scope = { accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end };
  const { data, error, loading } = useApi<DashboardData>(
    `dashboard:${JSON.stringify([filters.accounts, filters.statuses, filters.start, filters.end])}`,
    async () => {
      const [dashboard, monthly, analyticData, imports] = await Promise.all([
        loadDashboard(scope),
        loadMonthlyKpi(scope),
        loadAnalytics(scope),
        loadImportHistory(5, filters.accounts),
      ]);
      return { overview: dashboard.overview, daily: dashboard.daily, kpi: monthly.items, analytics: analyticData, history: imports.items };
    },
    "Không thể tải dashboard.",
  );

  if (error) return <Notice text={error} />;
  if (loading || !data) return <Skeleton rows={4} tall label="Đang tải số liệu dashboard" />;
  const { overview, daily, kpi, analytics, history } = data;
  const total = filters.accounts.length === 1 ? overview.find((row) => row.account === filters.accounts[0]) : overview.find((row) => row.account === "ALL");
  const activeKpi = filters.accounts.length === 1 ? kpi.find((row) => row.account === filters.accounts[0]) : kpi.find((row) => row.account === "ALL");
  const summary = analytics?.summary;
  const previous = analytics?.previous_period?.summary;
  const orderDelta = previous ? (summary?.orders ?? 0) - previous.orders : null;
  const commissionDelta = previous ? (summary?.actual_commission ?? 0) - previous.actual_commission : null;
  const progress = Math.max(0, Math.min((activeKpi?.target_achievement ?? 0) * 100, 100));
  const combinedProgress = Math.max(0, Math.min((activeKpi?.combined_target_achievement ?? 0) * 100, 100));
  const gap = activeKpi?.gap == null ? null : Math.max(-Number(activeKpi.gap), 0);
  const selectedLabel = filters.accounts.length ? filters.accounts.join(" + ") : accountLabel("ALL");
  const quality = analytics?.data_quality;
  // Không có gì bất thường thì đây là dòng thông tin, không phải cảnh báo — đừng tô vàng.
  const dataQualityClean = !quality || (quality.unknown_status_rows + quality.non_vnd_rows + quality.missing_settlement_date_rows + quality.import_rejected) === 0;
  const unknownOrdersHref = `/orders${queryString({ month: filters.month, start: filters.start, end: filters.end, account: filters.accounts, status: "unknown" })}`;

  // Chưa nhập file nào thì một dàn thẻ 0 đồng không nói lên điều gì; chỉ đường ba bước đầu tiên.
  // Chỉ tính là "chưa có gì" khi đang xem toàn bộ tài khoản — lọc sang một account trống trong
  // khi account khác vẫn có dữ liệu thì phải hiện số 0 bình thường, không phải màn hình khởi đầu.
  const wholeScope = filters.accounts.length === 0 || filters.accounts.length === accounts.length;
  if (wholeScope && !history.length && (summary?.order_lines ?? 0) === 0) return <FirstRun />;

  return (
    <>
      {/* Một lưới đều chín ô thay cho bốn thẻ lớn cộng một dải phụ khác kiểu: cùng cỡ chữ, cùng
          cách xuống dòng thì quét mắt một lượt là đọc hết, không phải đổi cách đọc giữa chừng. */}
      <section className="hero-grid" aria-label="Chỉ số kỳ báo cáo">
        <Metric title="Hoa hồng thực tế" value={formatMoney(summary?.actual_commission ?? activeKpi?.actual_commission)} hint={`${selectedLabel} · kỳ trước ${commissionDelta == null ? "—" : formatMoney(commissionDelta)}`} />
        <Metric title="GMV thực tế" value={formatMoney(summary?.actual_gmv ?? total?.actual_gmv)} hint={`kỳ trước ${orderDelta == null ? "—" : integer.format(orderDelta)} đơn`} />
        <article className="metric progress-metric panel"><span>Tiến độ mục tiêu</span><strong data-tone={achievementTone(activeKpi?.target_achievement)}>{percent(activeKpi?.target_achievement)}</strong><div className="progress-track" data-tone={achievementTone(activeKpi?.target_achievement)} role="progressbar" aria-label="Tiến độ hoa hồng" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number(progress.toFixed(1))}><span style={{ width: `${progress}%` }} /></div><small>Mục tiêu trong kỳ {formatMoney(activeKpi?.monthly_target)}</small></article>
        <Metric
          title={analytics?.target?.projected_month_end == null ? "Còn thiếu" : "Dự báo cuối tháng"}
          value={formatMoney(analytics?.target?.projected_month_end ?? analytics?.target?.remaining ?? gap)}
          hint={`Còn thiếu ${formatMoney(analytics?.target?.remaining ?? gap)} · cần/ngày ${formatMoney(analytics?.target?.required_per_remaining_day)}`}
          tone="warning"
        />
        <Metric title="Đơn hàng" value={summary ? integer.format(summary.orders) : total ? integer.format(total.orders) : "—"} hint={`${summary ? integer.format(summary.order_lines) : total ? integer.format(total.order_lines) : "—"} dòng`} />
        <Metric title="GMV gốc" value={formatMoney(summary?.gross_gmv ?? total?.gmv)} hint={`tỷ lệ HH ${percent(summary?.effective_commission_rate)}`} />
        <Metric title="Đã nhận cuối cùng" value={formatMoney(summary?.final_received ?? total?.final_received)} hint={`lệch HH ${formatMoney(summary?.final_received_variance)}`} />
        <Metric title="Hoàn tiền" value={percent(summary?.refund_rate)} hint={`không đủ điều kiện ${percent(summary?.ineligible_rate)}`} />
        <article className="metric progress-metric panel" title="Gồm cả đơn Không đủ điều kiện — phản ánh sức bán thật sự, KHÔNG phải tiền chắc chắn sẽ nhận."><span>Tiến độ gộp</span><strong data-tone={achievementTone(activeKpi?.combined_target_achievement)}>{percent(activeKpi?.combined_target_achievement)}</strong><div className="progress-track" data-tone={achievementTone(activeKpi?.combined_target_achievement)} role="progressbar" aria-label="Tiến độ hoa hồng gộp" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number(combinedProgress.toFixed(1))}><span style={{ width: `${combinedProgress}%` }} /></div><small>mất {formatMoney(activeKpi?.ineligible_commission)} do không đủ điều kiện</small></article>
      </section>
      {analytics ? <section className={`notice data-quality-notice${dataQualityClean ? " is-clean" : ""}`} role="status"><strong>Cập nhật gần nhất: {formatDateTime(analytics.data_quality.latest_import_at)}</strong><span>Trạng thái chưa xác định: <Link href={unknownOrdersHref}>{integer.format(analytics.data_quality.unknown_status_rows)} dòng</Link> · Tiền tệ khác VND: {integer.format(analytics.data_quality.non_vnd_rows)} · Thiếu ngày quyết toán: {integer.format(analytics.data_quality.missing_settlement_date_rows)} · Dòng nhập bị từ chối: <Link href="/imports">{integer.format(analytics.data_quality.import_rejected)} dòng</Link></span></section> : null}
      <div className="content-grid stacked">
        <RecentImports rows={history} />
        <AccountComparison rows={overview.filter((row) => row.account !== "ALL")} kpi={kpi} />
        <BarChart title="Nhịp ngày" description="Hoa hồng thực tế 14 ngày gần nhất." rows={daily.filter((row) => row.account === "ALL").slice(0, 14)} />
      </div>
    </>
  );
}


function FirstRun() {
  const steps = [
    { href: "/accounts", title: "Tạo tài khoản TikTok", copy: "Mỗi tài khoản affiliate là một phạm vi báo cáo riêng. File TikTok không nói nó thuộc tài khoản nào, nên bạn phải tạo trước." },
    { href: "/imports", title: "Nhập file Excel đầu tiên", copy: "Chọn tài khoản rồi tải file .xlsx xuất từ TikTok Affiliate. Nhập trùng file cũ cũng không làm số liệu nhân đôi." },
    { href: "/targets", title: "Đặt KPI mỗi ngày", copy: "Có KPI thì dashboard mới tính được tiến độ, phần còn thiếu và mức cần đạt mỗi ngày." },
  ];
  return (
    <section className="section panel first-run">
      <div className="section-heading"><div><p className="section-label">Bắt đầu</p><h2>Chưa có dữ liệu nào để báo cáo</h2><p>Ba bước dưới đây là toàn bộ những gì cần làm để dashboard có số.</p></div></div>
      <ol className="first-run-steps">
        {steps.map((step, index) => (
          <li key={step.href}>
            <span className="step-index" aria-hidden="true">{index + 1}</span>
            <div>
              <Link href={step.href}><strong>{step.title}</strong></Link>
              <p>{step.copy}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function AccountComparison({ rows, kpi }: { rows: OverviewRow[]; kpi: MonthlyKpiRow[] }) {
  const kpiMap = new Map(kpi.map((row) => [row.account, row]));
  return <section className="section panel wide" id="accounts"><div className="section-heading"><div><p className="section-label">Theo tài khoản</p><h2>So sánh hiệu suất</h2></div></div><div className="table-wrap" role="region" aria-label="Bảng so sánh hiệu suất tài khoản, có thể cuộn ngang" tabIndex={0}>{rows.length ? <table><thead><tr><th>Tài khoản</th><th>Đơn</th><th>SL bán</th><th>GMV</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Mục tiêu</th><th>Đã đạt</th></tr></thead><tbody>{rows.map((row) => { const achievement = kpiMap.get(row.account)?.target_achievement; return <tr key={row.account}><td>{row.account}</td><td>{integer.format(row.orders)}</td><td>{integer.format(row.units_sold)}</td><td>{formatMoney(row.gmv)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(kpiMap.get(row.account)?.monthly_target)}</td><td><span className="tone-text" data-tone={achievementTone(achievement)}>{percent(achievement)}</span></td></tr>; })}</tbody></table> : <p className="empty">Chưa có dữ liệu tài khoản trong bộ lọc. Hãy nhập file TikTok hoặc đổi phạm vi ngày.</p>}</div></section>;
}
