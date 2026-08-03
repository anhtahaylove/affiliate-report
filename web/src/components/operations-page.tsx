"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AdminUser,
  ApiError,
  AccountDeletePreview,
  AnalyticsDimensionRow,
  AnalyticsResponse,
  AccountItem,
  BackupItem,
  CurrentUser,
  DailyRow,
  ImportHistoryRow,
  MonthlyKpiRow,
  OrderRow,
  OverviewRow,
  TargetRow,
  UpdateStatus,
  checkUpdate,
  createAccount,
  deleteAccount,
  installUpdate,
  loadAnalytics,
  loadAccounts,
  loadBackups,
  loadCurrentUser,
  loadDashboard,
  loadImportHistory,
  loadMeta,
  loadMonthlyKpi,
  loadOrders,
  loadTargets,
  loadUsers,
  ordersExportUrl,
  previewDeleteAccount,
  resetData,
  restoreBackup,
  saveTarget,
  updateUser,
  updateAccount,
  uploadExport,
} from "@/lib/api";
import { AppShell, AuthCard } from "@/components/app-shell";
import { FilterBar, useUrlFilters } from "@/components/filters";
import { accountLabel, countsText, errorMessage, formatBytes, formatDateTime, formatMoney, integer, percent, roleLabel, statusLabel } from "@/lib/format";

type RouteKind = "dashboard" | "analytics" | "orders" | "imports" | "targets" | "accounts" | "data" | "update" | "users";
type UrlFilters = ReturnType<typeof useUrlFilters>;
const ORDER_PAGE_SIZE = 100;

const routeMeta: Record<RouteKind, { label: string; title: string; copy: string; needsWrite?: boolean; needsOwner?: boolean; filters?: boolean; search?: boolean }> = {
  dashboard: { label: "Tổng quan", title: "Tổng quan hiệu suất", copy: "Theo dõi hoa hồng, tiến độ mục tiêu và phạm vi dữ liệu hiện tại.", filters: true },
  analytics: { label: "Phân tích", title: "Phân tích xu hướng", copy: "Phân tích tài chính, sản phẩm, cửa hàng, nội dung, quyết toán và chất lượng dữ liệu.", filters: true },
  orders: { label: "Đơn hàng", title: "Tra cứu đơn hàng", copy: "Tìm kiếm, lọc và xuất Excel toàn bộ đơn hàng theo phạm vi hiện tại.", filters: true, search: true },
  imports: { label: "Nhập dữ liệu", title: "Nhập file TikTok", copy: "Chọn tài khoản TikTok và nhập nhiều file Excel tuần tự; hệ thống báo kết quả từng file.", needsWrite: true },
  targets: { label: "Mục tiêu", title: "Mục tiêu theo tài khoản", copy: "Điều chỉnh KPI mỗi ngày theo tháng; mục tiêu tháng được hệ thống tự tính.", filters: true },
  accounts: { label: "Tài khoản", title: "Quản lý tài khoản TikTok", copy: "Quản lý toàn bộ tài khoản; bộ lọc chỉ áp dụng cho phần so sánh hiệu suất.", needsOwner: true, filters: true },
  data: { label: "Dữ liệu", title: "Xóa và khôi phục dữ liệu", copy: "Chỉ chủ sở hữu được thao tác; hệ thống luôn tạo bản sao lưu an toàn trước khi thay đổi.", needsOwner: true },
  update: { label: "Cập nhật", title: "Cập nhật ứng dụng", copy: "Kiểm tra nguồn cập nhật công khai đã ký và cài phiên bản mới trong ứng dụng Windows.", needsOwner: true },
  users: { label: "Người dùng", title: "Quản lý người dùng", copy: "Phân quyền vai trò và phạm vi tài khoản cho từng người dùng.", needsOwner: true },
};

function canWrite(user: CurrentUser | null) {
  return user?.role === "operator" || user?.role === "owner";
}

function isOwner(user: CurrentUser | null) {
  return user?.role === "owner";
}

function csvCell(value: unknown) {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(name: string, rows: OrderRow[]) {
  const columns: Array<keyof OrderRow> = ["account", "order_id", "sku_id", "product_name", "shop_name", "status", "order_date", "gmv", "units_sold", "units_refunded", "estimated_commission", "final_received", "version", "created_at"];
  const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function updateErrorMessage(reason: unknown) {
  const message = errorMessage(reason, "Không thể kiểm tra cập nhật.");
  if (reason instanceof ApiError && [401, 403, 404, 502].includes(reason.status)) {
    return `${message} Public signed feed không dùng token; kiểm tra URL feed, chữ ký và kết nối mạng.`;
  }
  return message;
}

export function OperationsPage({ route }: { route: RouteKind }) {
  const filters = useUrlFilters();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [maxUploadMb, setMaxUploadMb] = useState(50);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [currentUser, meta] = await Promise.all([loadCurrentUser(), loadMeta()]);
        if (!active) return;
        setUser(currentUser);
        setAccounts(meta.accounts);
        setStatuses(meta.statuses);
        setMaxUploadMb(meta.max_upload_mb);
        setApiError("");
      } catch (reason) {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 401) setAuthError(reason.message || "Phiên đăng nhập đã hết hạn.");
        else setApiError(errorMessage(reason, "Không thể tải cấu hình API."));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  if (loading) return <main className="auth-shell"><section className="auth-card panel"><div className="brand-badge">AFF</div><h1>Đang tải trung tâm vận hành…</h1><p className="hint">Đang kiểm tra phiên đăng nhập và kết nối dữ liệu.</p></section></main>;
  if (authError || !user) return <AuthCard message={authError || "Chưa xác thực."} />;
  const meta = routeMeta[route];
  if (meta.needsWrite && !canWrite(user)) return <AppShell user={user} apiError={apiError}><Notice text="Bạn không có quyền nhập dữ liệu. Hãy liên hệ chủ sở hữu để được cấp quyền." /></AppShell>;
  if (meta.needsOwner && !isOwner(user)) return <AppShell user={user} apiError={apiError}><Notice text="Chỉ chủ sở hữu được truy cập trang này." /></AppShell>;

  return (
    <AppShell user={user} apiError={apiError}>
      <div className="page-heading"><p className="section-label">{meta.label}</p><h1>{meta.title}</h1><p className="subtle">{meta.copy}</p></div>
      {meta.filters ? <FilterBar accounts={accounts} statuses={route === "targets" ? [] : statuses} showSearch={meta.search} /> : null}
      {route === "dashboard" ? <DashboardHome filters={filters} /> : null}
      {route === "analytics" ? <AnalyticsPage filters={filters} /> : null}
      {route === "orders" ? <OrdersPage filters={filters} /> : null}
      {route === "imports" ? <ImportsPage user={user} accounts={accounts} maxUploadMb={maxUploadMb} /> : null}
      {route === "targets" ? <TargetsPage user={user} filters={filters} accounts={accounts} /> : null}
      {route === "accounts" ? <AccountsPage filters={filters} /> : null}
      {route === "data" ? <DataSettingsPage /> : null}
      {route === "update" ? <UpdateSettingsPage /> : null}
      {route === "users" ? <UsersSettingsPage currentUser={user} accounts={accounts} /> : null}
    </AppShell>
  );
}

function Notice({ text }: { text: string }) {
  return <section className="notice" role="alert">{text}</section>;
}

function StateCard({ text }: { text: string }) {
  return <section className="section panel"><p className="empty">{text}</p></section>;
}

function Metric({ title, value, hint }: { title: string; value: string; hint: string }) {
  return <article className="metric panel"><span>{title}</span><strong>{value}</strong><small>{hint}</small></article>;
}

function StatusBadge({ status }: { status: string | null | undefined }) {
  return <span className="status-badge" data-status={status ?? "unknown"} title={status ? `Mã hệ thống: ${status}` : undefined}>{statusLabel(status)}</span>;
}

function DashboardHome({ filters }: { filters: UrlFilters }) {
  const [overview, setOverview] = useState<OverviewRow[]>([]);
  const [daily, setDaily] = useState<DailyRow[]>([]);
  const [kpi, setKpi] = useState<MonthlyKpiRow[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [history, setHistory] = useState<ImportHistoryRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const [dashboard, monthly, analyticData, imports] = await Promise.all([
          loadDashboard({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end }),
          loadMonthlyKpi({ month: filters.month, accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end }),
          loadAnalytics({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end }),
          loadImportHistory(5, filters.accounts),
        ]);
        if (!active) return;
        setOverview(dashboard.overview);
        setDaily(dashboard.daily);
        setKpi(monthly.items);
        setAnalytics(analyticData);
        setHistory(imports.items);
        setError("");
      } catch (reason) {
        if (active) setError(errorMessage(reason, "Không thể tải dashboard."));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [filters.accounts, filters.end, filters.month, filters.start, filters.statuses]);

  if (loading) return <StateCard text="Đang tải số liệu dashboard…" />;
  if (error) return <Notice text={error} />;
  const total = filters.accounts.length === 1 ? overview.find((row) => row.account === filters.accounts[0]) : overview.find((row) => row.account === "ALL");
  const activeKpi = filters.accounts.length === 1 ? kpi.find((row) => row.account === filters.accounts[0]) : kpi.find((row) => row.account === "ALL");
  const summary = analytics?.summary;
  const previous = analytics?.previous_period?.summary;
  const orderDelta = previous ? (summary?.orders ?? 0) - previous.orders : null;
  const commissionDelta = previous ? (summary?.actual_commission ?? 0) - previous.actual_commission : null;
  const progress = Math.max(0, Math.min((activeKpi?.target_achievement ?? 0) * 100, 100));
  const gap = activeKpi?.gap == null ? null : Math.max(-Number(activeKpi.gap), 0);
  const selectedLabel = filters.accounts.length ? filters.accounts.join(" + ") : accountLabel("ALL");

  return (
    <>
      <section className="hero-grid" aria-label="Tổng quan KPI">
        <Metric title="Đơn hàng" value={summary ? integer.format(summary.orders) : total ? integer.format(total.orders) : "—"} hint={`${summary ? integer.format(summary.order_lines) : total ? integer.format(total.order_lines) : "—"} dòng · kỳ trước ${orderDelta == null ? "—" : integer.format(orderDelta)}`} />
        <Metric title="GMV thực tế" value={formatMoney(summary?.actual_gmv ?? total?.actual_gmv)} hint={`GMV gốc ${formatMoney(summary?.gross_gmv ?? total?.gmv)}`} />
        <Metric title="Hoa hồng thực tế" value={formatMoney(summary?.actual_commission ?? activeKpi?.actual_commission)} hint={`${selectedLabel} · tỷ lệ HH ${percent(summary?.effective_commission_rate)} · kỳ trước ${commissionDelta == null ? "—" : formatMoney(commissionDelta)}`} />
        <Metric title="Đã nhận cuối cùng" value={formatMoney(summary?.final_received ?? total?.final_received)} hint={`Lệch HH ${formatMoney(summary?.final_received_variance)} · hoàn ${percent(summary?.refund_rate)} · loại ${percent(summary?.ineligible_rate)}`} />
        <article className="metric progress-metric panel"><span>Tiến độ mục tiêu</span><strong>{percent(activeKpi?.target_achievement)}</strong><div className="progress-track" role="progressbar" aria-label="Tiến độ hoa hồng" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number(progress.toFixed(1))}><span style={{ width: `${progress}%` }} /></div><small>Mục tiêu tháng {formatMoney(activeKpi?.monthly_target)}</small></article>
        <article className="metric danger-metric panel"><span>{analytics?.target?.projected_month_end == null ? "Còn thiếu" : "Dự báo cuối tháng"}</span><strong>{formatMoney(analytics?.target?.projected_month_end ?? analytics?.target?.remaining ?? gap)}</strong><small>Còn thiếu {formatMoney(analytics?.target?.remaining ?? gap)} · cần/ngày {formatMoney(analytics?.target?.required_per_remaining_day)}</small></article>
      </section>
      {analytics ? <section className="notice data-quality-notice" role="status"><strong>Cập nhật gần nhất: {formatDateTime(analytics.data_quality.latest_import_at)}</strong><span>Trạng thái chưa xác định: {integer.format(analytics.data_quality.unknown_status_rows)} · Tiền tệ khác VND: {integer.format(analytics.data_quality.non_vnd_rows)} · Thiếu ngày quyết toán: {integer.format(analytics.data_quality.missing_settlement_date_rows)} · Dòng nhập bị từ chối: {integer.format(analytics.data_quality.import_rejected)}</span></section> : null}
      <div className="content-grid">
        <RecentImports rows={history} />
        <AccountComparison rows={overview.filter((row) => row.account !== "ALL")} kpi={kpi} />
        <DailyTable rows={daily.filter((row) => row.account === "ALL").slice(0, 14)} />
      </div>
    </>
  );
}

function AnalyticsPage({ filters }: { filters: UrlFilters }) {
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const payload = await loadAnalytics({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end });
        if (!active) return;
        setData(payload);
        setError("");
      } catch (reason) {
        if (active) setError(errorMessage(reason, "Không thể tải phân tích."));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [filters.accounts, filters.end, filters.start, filters.statuses]);
  if (loading) return <StateCard text="Đang tải phân tích…" />;
  if (error) return <Notice text={error} />;
  if (!data) return <StateCard text="Chưa có dữ liệu phân tích." />;
  const summary = data.summary;
  const previous = data.previous_period?.summary;
  const commissionDelta = previous ? summary.actual_commission - previous.actual_commission : null;
  return (
    <div className="content-grid">
      <section className="hero-grid wide" aria-label="Tóm tắt analytics">
        <Metric title="Đơn / dòng" value={`${integer.format(summary.orders)} / ${integer.format(summary.order_lines)}`} hint={`Kỳ trước ${previous ? integer.format(previous.orders) : "—"} đơn`} />
        <Metric title="Hoa hồng" value={formatMoney(summary.actual_commission)} hint={`So kỳ trước ${commissionDelta == null ? "—" : formatMoney(commissionDelta)}`} />
        <Metric title="Đã nhận" value={formatMoney(summary.final_received)} hint={`Lệch ${formatMoney(summary.final_received_variance)}`} />
        <Metric title="Tỷ lệ hoa hồng hiệu dụng" value={percent(summary.effective_commission_rate)} hint={`Hoàn tiền ${percent(summary.refund_rate)} · không đủ điều kiện ${percent(summary.ineligible_rate)}`} />
        <Metric title="Dự báo mục tiêu" value={formatMoney(data.target?.projected_month_end)} hint={`Cần/ngày ${formatMoney(data.target?.required_per_remaining_day)} · dự kiến đạt ${percent(data.target?.projected_achievement)}`} />
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

function AnalyticsTrend({ rows }: { rows: AnalyticsResponse["trend"] }) {
  const chartRows = rows.slice(-30);
  const max = Math.max(...chartRows.map((row) => row.actual_commission), 1);
  const step = chartRows.length ? 90 / chartRows.length : 90;
  return (
    <section className="section panel wide">
      <div className="section-heading"><div><p className="section-label">Xu hướng tài chính</p><h2>Hoa hồng theo kỳ</h2></div></div>
      {rows.length ? (
        <>
          <svg className="analytics-svg" viewBox="0 0 100 40" role="img" aria-labelledby="analytics-trend-title analytics-trend-desc" preserveAspectRatio="none">
            <title id="analytics-trend-title">Hoa hồng thực tế theo kỳ</title>
            <desc id="analytics-trend-desc">Biểu đồ cột của tối đa 30 kỳ gần nhất; bảng ngay sau biểu đồ chứa dữ liệu đầy đủ.</desc>
            <line x1="5" y1="36" x2="95" y2="36" className="analytics-axis" />
            {chartRows.map((row, index) => {
              const height = Math.max((row.actual_commission / max) * 31, 0.8);
              return <rect key={row.period} x={5 + index * step + step * 0.12} y={36 - height} width={step * 0.76} height={height} rx="0.8"><title>{`${row.period}: ${formatMoney(row.actual_commission)}`}</title></rect>;
            })}
          </svg>
          <div className="table-wrap chart-fallback" role="region" aria-label="Bảng xu hướng hoa hồng, có thể cuộn ngang" tabIndex={0}><table><thead><tr><th>Kỳ</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Đã nhận</th></tr></thead><tbody>{rows.map((row) => <tr key={row.period}><td>{row.period}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(row.final_received)}</td></tr>)}</tbody></table></div>
        </>
      ) : <p className="empty">Chưa có dữ liệu xu hướng trong bộ lọc.</p>}
    </section>
  );
}

function AnalyticsBreakdown({ title, rows, labelKey }: { title: string; rows: AnalyticsResponse["status_breakdown"]; labelKey: "status" | "account" }) {
  return (
    <section className="section panel">
      <div className="section-heading"><div><p className="section-label">Phân bổ</p><h2>{title}</h2></div></div>
      <div className="table-wrap" role="region" aria-label={`${title}, có thể cuộn ngang`} tabIndex={0}>{rows.length ? <table><thead><tr><th>{labelKey === "status" ? "Trạng thái" : "Tài khoản"}</th><th>Đơn</th><th>GMV</th><th>Hoa hồng</th><th>Tỷ trọng HH</th></tr></thead><tbody>{rows.map((row) => <tr key={row[labelKey] ?? "unknown"}><td>{labelKey === "status" ? <StatusBadge status={row.status} /> : accountLabel(row.account)}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{percent(row.commission_share)}</td></tr>)}</tbody></table> : <p className="empty">Chưa có dữ liệu {title.toLowerCase()}.</p>}</div>
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

function OrdersPage({ filters }: { filters: UrlFilters }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const data = await loadOrders({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end, search: filters.search, limit: ORDER_PAGE_SIZE, offset: (filters.page - 1) * ORDER_PAGE_SIZE });
        if (!active) return;
        const lastPage = Math.max(1, Math.ceil(data.total / ORDER_PAGE_SIZE));
        if (filters.page > lastPage) {
          const query = new URLSearchParams(searchParams.toString());
          query.set("page", String(lastPage));
          router.replace(`${pathname}?${query.toString()}`);
          return;
        }
        setOrders(data.items);
        setTotal(data.total);
        setError("");
      } catch (reason) {
        if (active) setError(errorMessage(reason, "Không thể tải đơn hàng."));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [filters.accounts, filters.end, filters.page, filters.search, filters.start, filters.statuses, pathname, router, searchParams]);
  if (loading) return <StateCard text="Đang tải đơn hàng…" />;
  if (error) return <Notice text={error} />;
  const totalPages = Math.max(1, Math.ceil(total / ORDER_PAGE_SIZE));
  function goToPage(page: number) {
    const query = new URLSearchParams(searchParams.toString());
    query.set("page", String(Math.max(1, Math.min(page, totalPages))));
    router.push(`${pathname}?${query.toString()}`);
  }
  return (
    <section className="section panel wide">
      <div className="section-heading"><div><p className="section-label">Danh sách đơn hàng</p><h2>{integer.format(total)} đơn trong bộ lọc</h2></div><div className="row-actions"><a className="button-link" download="tiktok-affiliate-orders.xlsx" href={ordersExportUrl({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end, search: filters.search })}>Xuất toàn bộ ra Excel</a><button type="button" onClick={() => downloadCsv(`orders-${filters.start}-${filters.end}.csv`, orders)} disabled={!orders.length}>Xuất CSV trang này</button></div></div>
      <div className="table-wrap orders-table" role="region" aria-label="Danh sách đơn hàng, có thể cuộn ngang" tabIndex={0}><table><thead><tr><th>Tài khoản</th><th>Mã đơn</th><th>SKU</th><th>Sản phẩm</th><th>Trạng thái</th><th>Ngày</th><th>GMV</th><th>Hoa hồng</th><th>Chi tiết</th></tr></thead><tbody>{orders.map((row, index) => <tr key={`${row.account}-${row.order_id}-${row.sku_id}-${index}`}><td>{row.account}</td><td>{row.order_id ?? "—"}</td><td>{row.sku_id ?? "—"}</td><td className="product-cell" title={row.product_name ?? undefined}>{row.product_name ?? "—"}</td><td><StatusBadge status={row.status} /></td><td>{row.order_date ?? "—"}</td><td>{formatMoney(row.gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td><details className="order-detail"><summary>{`Chi tiết ${row.order_id ?? row.sku_id ?? index + 1}`}</summary><span>ID sản phẩm: {row.product_id ?? "—"}</span><span>Cửa hàng: {row.shop_name ?? "—"} ({row.shop_id ?? "—"})</span><span>Nội dung: {row.content_type ?? "—"} / {row.content_id ?? "—"}</span><span>Loại đơn: {row.order_type ?? "—"}</span><span>Loại hoa hồng: {row.commission_type ?? "—"}</span><span>Ngày quyết toán: {row.settlement_date ?? "—"}</span><span>Đã nhận: {formatMoney(row.final_received)}</span></details></td></tr>)}</tbody></table>{!orders.length ? <p className="empty">Không có đơn phù hợp. Hãy đổi bộ lọc hoặc nhập thêm file TikTok.</p> : null}</div>
      <nav className="pagination" aria-label="Phân trang đơn hàng"><button type="button" onClick={() => goToPage(filters.page - 1)} disabled={filters.page <= 1}>Trang trước</button><span>Trang {integer.format(filters.page)} / {integer.format(totalPages)}</span><button type="button" onClick={() => goToPage(filters.page + 1)} disabled={filters.page >= totalPages}>Trang sau</button></nav>
    </section>
  );
}

function ImportsPage({ user, accounts, maxUploadMb }: { user: CurrentUser; accounts: string[]; maxUploadMb: number }) {
  const [account, setAccount] = useState(accounts[0] ?? "");
  const [files, setFiles] = useState<FileList | null>(null);
  const [history, setHistory] = useState<ImportHistoryRow[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const refreshHistory = useCallback(async () => {
    const data = await loadImportHistory(20);
    setHistory(data.items);
  }, []);
  useEffect(() => {
    async function load() {
      try { await refreshHistory(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải lịch sử import.")); }
    }
    void load();
  }, [refreshHistory]);
  async function submit() {
    if (!canWrite(user)) return setMessage("Tài khoản chỉ xem không có quyền nhập dữ liệu.");
    if (!account || !files?.length) return setMessage("Hãy chọn tài khoản và ít nhất một file .xlsx.");
    setBusy(true);
    const results: string[] = [];
    try {
      for (const file of Array.from(files)) {
        if (!file.name.toLowerCase().endsWith(".xlsx")) { results.push(`${file.name}: bỏ qua vì không phải .xlsx`); continue; }
        const result = await uploadExport(account, file);
        const imported = result.inserted + result.updated + result.unchanged;
        results.push(result.duplicate ? `${file.name}: đã import trước đó, không nhân đôi` : `${file.name}: ${integer.format(imported)} dòng, lỗi ${integer.format(result.rejected)}`);
      }
      setMessage(results.join(" · "));
      await refreshHistory();
    } catch (reason) {
      setMessage(errorMessage(reason, "Nhập dữ liệu thất bại."));
    } finally {
      setBusy(false);
    }
  }
  return <div className="content-grid"><section className="section panel"><div className="section-heading"><div><p className="section-label">Nhập tuần tự</p><h2>Chọn nhiều file TikTok</h2><p>Tối đa {integer.format(maxUploadMb)} MB mỗi file; chỉ hỗ trợ định dạng .xlsx.</p></div></div><div className="upload-form"><div className="field"><label htmlFor="import-account">Tài khoản TikTok</label><select id="import-account" value={account} onChange={(event) => setAccount(event.target.value)}>{accounts.map((item) => <option key={item}>{item}</option>)}</select></div><div className="field dropzone"><label htmlFor="import-files">File Excel đã xuất từ TikTok</label><input id="import-files" type="file" multiple accept=".xlsx" onChange={(event) => setFiles(event.target.files)} /><span>Có thể chọn nhiều file; hệ thống sẽ nhập lần lượt và tự chống trùng.</span></div><button className="primary" type="button" onClick={() => void submit()} disabled={busy}>{busy ? "Đang nhập…" : "Nhập dữ liệu"}</button>{message ? <p className="upload-result" role="status">{message}</p> : null}</div></section><RecentImports rows={history} /></div>;
}

function TargetsPage({ user, filters, accounts }: { user: CurrentUser; filters: UrlFilters; accounts: string[] }) {
  const [targets, setTargets] = useState<TargetRow[]>([]);
  const [kpi, setKpi] = useState<MonthlyKpiRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState("");
  const [message, setMessage] = useState("");
  const scopedAccounts = filters.accounts.length ? accounts.filter((account) => filters.accounts.includes(account)) : accounts;
  const allowedAccounts = user.role === "owner" ? ["ALL", ...scopedAccounts] : scopedAccounts;
  const refresh = useCallback(async () => {
    const [targetData, monthly] = await Promise.all([
      loadTargets(filters.month),
      loadMonthlyKpi({ month: filters.month, accounts: filters.accounts, start: filters.start, end: filters.end }),
    ]);
    setTargets(targetData.items);
    setDrafts(Object.fromEntries(targetData.items.map((item) => [item.account, String(item.target_commission)])));
    setKpi(monthly.items);
  }, [filters.accounts, filters.end, filters.month, filters.start]);
  useEffect(() => {
    async function load() {
      try { await refresh(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải mục tiêu.")); }
    }
    void load();
  }, [refresh]);
  async function save(account: string) {
    const draft = (drafts[account] ?? "").trim();
    if (!/^\d+$/.test(draft)) return setMessage("KPI/ngày phải là số nguyên không âm.");
    setSaving(account);
    try {
      await saveTarget(account, filters.month, Number(draft));
      setMessage(`Đã lưu KPI/ngày cho ${account}.`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể lưu mục tiêu."));
    } finally {
      setSaving("");
    }
  }
  const targetMap = new Map(targets.map((target) => [target.account, target]));
  const kpiMap = new Map(kpi.map((row) => [row.account, row]));
  return <section className="section panel wide"><div className="section-heading"><div><p className="section-label">KPI mỗi ngày</p><h2>Mục tiêu tháng {filters.month}</h2></div>{!canWrite(user) ? <span className="read-only">Chỉ xem</span> : null}</div><div className="target-list">{allowedAccounts.map((account) => <div className="target-row" key={account}><div><strong>{accountLabel(account)}</strong><span>Hoa hồng {formatMoney(kpiMap.get(account)?.actual_commission)} · KPI/ngày {formatMoney(targetMap.get(account)?.target_commission)} · đã đạt {percent(kpiMap.get(account)?.target_achievement)}</span></div><input type="number" min="0" step="1" value={drafts[account] ?? ""} onChange={(event) => setDrafts((current) => ({ ...current, [account]: event.target.value }))} disabled={!canWrite(user) || saving === account} aria-label={`KPI ngày ${accountLabel(account)}`} /><button type="button" onClick={() => void save(account)} disabled={!canWrite(user) || saving === account}>{saving === account ? "Đang lưu…" : "Lưu"}</button></div>)}</div>{message ? <p className="upload-result" role="status">{message}</p> : null}</section>;
}

function AccountsPage({ filters }: { filters: UrlFilters }) {
  const [overview, setOverview] = useState<OverviewRow[]>([]);
  const [kpi, setKpi] = useState<MonthlyKpiRow[]>([]);
  const [records, setRecords] = useState<AccountItem[]>([]);
  const [hardDeleteSupported, setHardDeleteSupported] = useState(false);
  const [draft, setDraft] = useState({ code: "", display_name: "" });
  const [accountDrafts, setAccountDrafts] = useState<Record<string, { display_name: string; display_order: string }>>({});
  const [deletePreview, setDeletePreview] = useState<AccountDeletePreview | null>(null);
  const [deletePhrase, setDeletePhrase] = useState("");
  const [message, setMessage] = useState("");
  const refreshAccounts = useCallback(async () => {
    const data = await loadAccounts();
    setRecords(data.items);
    setAccountDrafts(Object.fromEntries(data.items.map((item) => [item.code, { display_name: item.display_name, display_order: String(item.display_order) }])));
    setHardDeleteSupported(data.hard_delete_supported);
  }, []);
  useEffect(() => {
    async function load() {
      try { await refreshAccounts(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải danh sách tài khoản.")); }
    }
    void load();
  }, [refreshAccounts]);
  useEffect(() => {
    let active = true;
    Promise.all([
      loadDashboard({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end }),
      loadMonthlyKpi({ month: filters.month, accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end }),
    ]).then(([dash, monthly]) => {
      if (!active) return;
      setOverview(dash.overview);
      setKpi(monthly.items);
    }).catch((reason) => setMessage(errorMessage(reason, "Không thể tải dữ liệu tài khoản.")));
    return () => { active = false; };
  }, [filters.accounts, filters.end, filters.month, filters.start, filters.statuses]);
  async function create() {
    const code = draft.code.trim().toUpperCase();
    const displayName = draft.display_name.trim() || code;
    if (!code) return setMessage("Hãy nhập mã tài khoản.");
    try {
      await createAccount({ code, display_name: displayName });
      setDraft({ code: "", display_name: "" });
      setMessage(`Đã tạo tài khoản ${code}.`);
      await refreshAccounts();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể tạo tài khoản."));
    }
  }
  async function patch(record: AccountItem, changes: Partial<AccountItem>) {
    try {
      await updateAccount(record.code, {
        display_name: changes.display_name,
        display_order: changes.display_order,
        active: changes.active,
      });
      setMessage(`Đã cập nhật ${record.code}.`);
      await refreshAccounts();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể cập nhật tài khoản."));
    }
  }

  async function saveAccount(record: AccountItem) {
    const current = accountDrafts[record.code];
    if (!current) return;
    const name = current.display_name.trim();
    const order = Number(current.display_order);
    if (!name) return setMessage("Tên hiển thị không được để trống.");
    if (!Number.isInteger(order)) return setMessage("Thứ tự hiển thị phải là số nguyên.");
    await patch(record, { display_name: name, display_order: order });
  }
  async function previewDelete(record: AccountItem) {
    try {
      const preview = await previewDeleteAccount(record.code);
      setDeletePreview(preview);
      setDeletePhrase("");
      setMessage(`Ảnh hưởng khi xóa ${record.code}: ${countsText(preview.dependency_counts)}.`);
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể xem trước ảnh hưởng khi xóa tài khoản."));
    }
  }
  async function confirmDelete() {
    if (!deletePreview) return;
    const expected = `XOA ${deletePreview.code}`;
    if (deletePhrase.trim() !== expected) return setMessage(`Nhập đúng ${expected}.`);
    if (!window.confirm(`${deletePreview.action === "hard_delete" ? "Xóa vĩnh viễn" : "Lưu trữ"} tài khoản ${deletePreview.code}?`)) return;
    try {
      const result = await deleteAccount(deletePreview.code, deletePhrase.trim());
      setMessage(result.hard_deleted ? `Đã xóa vĩnh viễn ${result.code}. Bản sao lưu: ${result.backup_path}.` : `Đã lưu trữ ${result.code}.`);
      setDeletePreview(null);
      setDeletePhrase("");
      await refreshAccounts();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể xóa tài khoản."));
    }
  }
  return (
    <div className="content-grid">
      <section className="section panel">
        <div className="section-heading">
          <div>
            <p className="section-label">Danh sách tài khoản</p>
            <h2>Thêm và quản lý tài khoản</h2>
            <p>{hardDeleteSupported ? "Có thể xóa vĩnh viễn sau khi tạo bản sao lưu." : "Dữ liệu dùng chung chỉ cho phép lưu trữ tài khoản; lịch sử vẫn được giữ lại."}</p>
          </div>
        </div>
        <div className="upload-form">
          <div className="field"><label htmlFor="new-account-code">Mã tài khoản</label><input id="new-account-code" value={draft.code} onChange={(event) => setDraft((current) => ({ ...current, code: event.target.value }))} placeholder="SHOP_1" /></div>
          <div className="field"><label htmlFor="new-account-name">Tên hiển thị</label><input id="new-account-name" value={draft.display_name} onChange={(event) => setDraft((current) => ({ ...current, display_name: event.target.value }))} placeholder="Cửa hàng 1" /></div>
          <button type="button" onClick={() => void create()}>Tạo tài khoản</button>
          {records.map((record) => {
            const rowDraft = accountDrafts[record.code] ?? { display_name: record.display_name, display_order: String(record.display_order) };
            return (
              <article className="import-item" key={record.code}>
                <div className="record-title"><strong>{record.display_name}</strong><span className="status-badge" data-status={record.active ? "active" : "archived"}>{record.active ? "Đang hoạt động" : "Đã lưu trữ"}</span></div>
                <span>{record.code} · thứ tự {record.display_order}</span>
                <div className="account-edit-grid">
                  <div className="field"><label htmlFor={`account-name-${record.code}`}>Tên hiển thị</label><input id={`account-name-${record.code}`} value={rowDraft.display_name} onChange={(event) => setAccountDrafts((current) => ({ ...current, [record.code]: { ...rowDraft, display_name: event.target.value } }))} /></div>
                  <div className="field"><label htmlFor={`account-order-${record.code}`}>Thứ tự hiển thị</label><input id={`account-order-${record.code}`} type="number" step="1" value={rowDraft.display_order} onChange={(event) => setAccountDrafts((current) => ({ ...current, [record.code]: { ...rowDraft, display_order: event.target.value } }))} /></div>
                </div>
                <div className="row-actions"><button type="button" onClick={() => void saveAccount(record)}>Lưu thay đổi</button><button type="button" onClick={() => void patch(record, { active: !record.active })}>{record.active ? "Lưu trữ" : "Kích hoạt lại"}</button><button type="button" className="danger-button" onClick={() => void previewDelete(record)}>Xem trước khi xóa</button></div>
              </article>
            );
          })}
          {deletePreview ? <div className="notice" role="alert"><strong>{deletePreview.action === "hard_delete" ? "Xem trước khi xóa vĩnh viễn" : "Xem trước khi lưu trữ"}: {deletePreview.code}</strong><p>{countsText(deletePreview.dependency_counts)}</p><div className="field"><label htmlFor="delete-account-confirm">Nhập chính xác <strong>XOA {deletePreview.code}</strong></label><input id="delete-account-confirm" value={deletePhrase} onChange={(event) => setDeletePhrase(event.target.value)} /></div><button type="button" className="danger-button" onClick={() => void confirmDelete()} disabled={deletePhrase.trim() !== `XOA ${deletePreview.code}`}>Xác nhận xóa</button></div> : null}
          {message ? <p className="upload-result" role="status">{message}</p> : null}
          {!records.length ? <p className="empty">Chưa có tài khoản. Hãy tạo tài khoản đầu tiên để bắt đầu nhập dữ liệu.</p> : null}
        </div>
      </section>
      <AccountComparison rows={overview.filter((row) => row.account !== "ALL")} kpi={kpi} />
    </div>
  );
}

function DataSettingsPage() {
  const [resetPhrase, setResetPhrase] = useState("");
  const [restorePhrase, setRestorePhrase] = useState("");
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
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
    if (resetPhrase.trim() !== "XOA DU LIEU") return setMessage("Nhập đúng XOA DU LIEU.");
    if (!window.confirm("Xóa toàn bộ lịch sử nhập và dữ liệu báo cáo? Hệ thống sẽ tự tạo bản sao lưu trước.")) return;
    setBusy(true);
    try {
      const result = await resetData(resetPhrase.trim());
      setResetPhrase("");
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
    if (restorePhrase.trim() !== "KHOI PHUC DU LIEU") return setMessage("Nhập đúng KHOI PHUC DU LIEU.");
    if (!window.confirm(`Khôi phục bản sao lưu ${selectedBackup.filename}? Dữ liệu hiện tại sẽ được sao lưu an toàn trước.`)) return;
    setBusy(true);
    try {
      const result = await restoreBackup(selectedBackup.id, restorePhrase.trim());
      setRestorePhrase("");
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
        <div className="reset-form"><div className="field"><label htmlFor="reset-confirmation">Nhập chính xác <strong>XOA DU LIEU</strong></label><input id="reset-confirmation" value={resetPhrase} onChange={(event) => setResetPhrase(event.target.value)} /></div><button className="danger-button" type="button" onClick={() => void doReset()} disabled={busy || resetPhrase.trim() !== "XOA DU LIEU"}>Xóa dữ liệu báo cáo</button></div>
      </section>
      <section className="section panel">
        <div className="section-heading"><div><p className="section-label">Bản sao lưu</p><h2>Khôi phục dữ liệu</h2><p>Xem trước thời gian, dung lượng và số lượng dữ liệu trước khi khôi phục.</p></div><button type="button" onClick={() => void refresh()} disabled={busy}>Tải lại danh sách</button></div>
        <div className="reset-form"><div className="backup-list" role="radiogroup" aria-label="Chọn bản sao lưu">{backups.map((backup) => <label className={`backup-item${backup.valid ? "" : " invalid"}`} key={backup.id}><input type="radio" checked={selected === backup.id} onChange={() => setSelected(backup.id)} disabled={!backup.valid || busy} /><span><strong>{backup.filename}</strong><small>{formatDateTime(backup.created_at)} · {formatBytes(backup.size_bytes)} · {backup.valid ? "Hợp lệ" : backup.error}</small><small>Dữ liệu báo cáo: {countsText(backup.counts.business)}</small><small>Tài khoản trong bản sao lưu: {countsText(backup.counts.auth)}</small></span></label>)}{!backups.length ? <p className="empty">Chưa có bản sao lưu. Hệ thống sẽ tự tạo trước lần xóa dữ liệu đầu tiên.</p> : null}</div><div className="field"><label htmlFor="restore-confirmation">Nhập chính xác <strong>KHOI PHUC DU LIEU</strong></label><input id="restore-confirmation" value={restorePhrase} onChange={(event) => setRestorePhrase(event.target.value)} /></div><button className="danger-button" type="button" onClick={() => void doRestore()} disabled={busy || restorePhrase.trim() !== "KHOI PHUC DU LIEU" || !selectedBackup?.valid}>Khôi phục bản sao lưu</button>{message ? <p className="reset-result" role="status">{message}</p> : null}</div>
      </section>
    </div>
  );
}

function UpdateSettingsPage() {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const check = useCallback(async () => {
    setBusy(true);
    try {
      const data = await checkUpdate();
      setStatus(data);
      setMessage(data.available ? `Có bản ${data.latest_version}${data.installable ? " sẵn sàng cài." : " nhưng chưa cài tự động được."}` : `Đang ở bản mới nhất (${data.current_version}).`);
    } catch (reason) {
      setStatus(null);
      setMessage(updateErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    async function load() {
      await check();
    }
    void load();
  }, [check]);
  async function install() {
    if (!status?.available || !status.installable || !status.automatic_install_supported) return;
    if (!window.confirm("Cài bản cập nhật ngay? Ứng dụng sẽ đóng và mở lại sau khi cài xong.")) return;
    setBusy(true);
    try {
      const result = await installUpdate("CAP NHAT UNG DUNG");
      setMessage(`Đang cài bản ${result.version}. Ứng dụng sẽ đóng và mở lại. SHA256: ${result.sha256}.`);
    } catch (reason) {
      setMessage(updateErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return <section className="section panel wide"><div className="section-heading"><div><p className="section-label">Phiên bản ứng dụng</p><h2>Kiểm tra và cài cập nhật</h2></div><button type="button" onClick={() => void check()} disabled={busy}>{busy ? "Đang kiểm tra…" : "Kiểm tra cập nhật"}</button></div><div className="update-panel"><div className="update-versions"><span>Đang dùng <strong>{status?.current_version ?? "—"}</strong></span><span>Mới nhất <strong>{status?.latest_version ?? "—"}</strong></span><span>Trạng thái <strong>{status ? (status.available ? "Có bản mới" : "Đã mới nhất") : "Chưa kiểm tra"}</strong></span></div>{status?.release_name ? <p><strong>{status.release_name}</strong></p> : null}{status?.published_at ? <p>Ngày phát hành: {formatDateTime(status.published_at)}</p> : null}{status?.source_repo ? <p className="source-repo">Nguồn cập nhật: {status.source_repo}</p> : null}{status?.notes ? <p className="update-notes" tabIndex={0}>{status.notes}</p> : null}{status?.release_url ? <a className="button-link secondary-link" href={status.release_url} target="_blank" rel="noreferrer">Xem trang phát hành</a> : null}{status && !status.automatic_install_supported ? <p className="hint">Cài tự động chỉ khả dụng trong bản Windows đã cài đặt.</p> : null}<button className="primary" type="button" onClick={() => void install()} disabled={!status?.available || !status.installable || !status.automatic_install_supported || busy}>Cài bản cập nhật</button><p className="hint">Ứng dụng sẽ đóng, cài đặt và tự mở lại sau khi hoàn tất.</p>{message ? <p className="upload-result" role="status">{message}</p> : null}</div></section>;
}

function UsersSettingsPage({ currentUser, accounts }: { currentUser: CurrentUser; accounts: string[] }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState<number | null>(null);
  const refresh = useCallback(async () => {
    const data = await loadUsers();
    setUsers(data.items);
  }, []);
  useEffect(() => {
    async function load() {
      try { await refresh(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải danh sách người dùng.")); }
    }
    void load();
  }, [refresh]);
  async function patch(user: AdminUser, changes: Partial<AdminUser>) {
    setSaving(user.id);
    try {
      await updateUser(user.id, changes);
      setMessage(`Đã cập nhật ${user.email}.`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể cập nhật người dùng."));
    } finally {
      setSaving(null);
    }
  }
  function toggleAccount(user: AdminUser, account: string) {
    const next = user.accounts.includes(account) ? user.accounts.filter((item) => item !== account) : [...user.accounts, account];
    void patch(user, { accounts: next });
  }
  return <section className="section panel wide"><div className="section-heading"><div><p className="section-label">Phân quyền truy cập</p><h2>Người dùng và phạm vi tài khoản</h2><p>Chủ sở hữu không thể tự hạ quyền hoặc tự ngừng kích hoạt tài khoản của mình.</p></div></div><div className="target-list">{users.map((user) => <article className="user-card" key={user.id}><div className="record-title"><div><strong>{user.display_name || user.email}</strong><span>{user.email}</span></div><span className="status-badge" data-status={user.active ? "active" : "archived"}>{user.active ? "Đang hoạt động" : "Đã lưu trữ"}</span></div><div className="row-actions"><label className="sr-only" htmlFor={`role-${user.id}`}>Vai trò của {user.email}</label><select id={`role-${user.id}`} value={user.role} onChange={(event) => void patch(user, { role: event.target.value as AdminUser["role"] })} disabled={saving === user.id || user.email === currentUser.email}><option value="owner">{roleLabel("owner")}</option><option value="operator">{roleLabel("operator")}</option><option value="viewer">{roleLabel("viewer")}</option></select><button type="button" onClick={() => void patch(user, { active: !user.active })} disabled={saving === user.id || user.email === currentUser.email}>{user.active ? "Lưu trữ" : "Kích hoạt lại"}</button></div>{user.role !== "owner" ? <fieldset className="filter-stack"><legend className="field-label">Tài khoản được truy cập</legend><div className="account-options">{accounts.map((account) => <label className="account-option" key={account}><input type="checkbox" checked={user.accounts.includes(account)} onChange={() => toggleAccount(user, account)} disabled={saving === user.id} />{account}</label>)}</div></fieldset> : <p className="hint">Chủ sở hữu có quyền truy cập tất cả tài khoản.</p>}</article>)}{!users.length ? <p className="empty">Chưa có người dùng nào.</p> : null}</div>{message ? <p className="upload-result" role="status">{message}</p> : null}</section>;
}

function RecentImports({ rows }: { rows: ImportHistoryRow[] }) {
  return <section className="section panel" id="recent-imports"><div className="section-heading"><div><p className="section-label">Lịch sử nhập dữ liệu</p><h2>Các lần nhập gần đây</h2></div></div><div className="import-list">{rows.length ? rows.map((item) => <article className="import-item" key={item.id}><strong>{item.filename}</strong><span>{item.account} · thêm {integer.format(item.inserted)} · cập nhật {integer.format(item.updated)} · trùng {integer.format(item.unchanged)} · lỗi {integer.format(item.rejected)}</span><time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time></article>) : <p className="empty">Chưa có lịch sử. Hãy nhập file TikTok đầu tiên để bắt đầu.</p>}</div></section>;
}

function AccountComparison({ rows, kpi }: { rows: OverviewRow[]; kpi: MonthlyKpiRow[] }) {
  const kpiMap = new Map(kpi.map((row) => [row.account, row]));
  return <section className="section panel wide" id="accounts"><div className="section-heading"><div><p className="section-label">Theo tài khoản</p><h2>So sánh hiệu suất</h2></div></div><div className="table-wrap" role="region" aria-label="Bảng so sánh hiệu suất tài khoản, có thể cuộn ngang" tabIndex={0}>{rows.length ? <table><thead><tr><th>Tài khoản</th><th>Đơn</th><th>GMV</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Mục tiêu</th><th>Đã đạt</th></tr></thead><tbody>{rows.map((row) => <tr key={row.account}><td>{row.account}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.gmv)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(kpiMap.get(row.account)?.monthly_target)}</td><td>{percent(kpiMap.get(row.account)?.target_achievement)}</td></tr>)}</tbody></table> : <p className="empty">Chưa có dữ liệu tài khoản trong bộ lọc. Hãy nhập file TikTok hoặc đổi phạm vi ngày.</p>}</div></section>;
}

function DailyTable({ rows }: { rows: DailyRow[] }) {
  return <section className="section panel wide"><div className="section-heading"><div><p className="section-label">Nhịp ngày</p><h2>14 ngày gần nhất</h2></div></div><div className="table-wrap" role="region" aria-label="Bảng hiệu suất 14 ngày gần nhất, có thể cuộn ngang" tabIndex={0}>{rows.length ? <table><thead><tr><th>Ngày</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Đạt KPI</th></tr></thead><tbody>{rows.map((row) => <tr key={row.day}><td>{row.day}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{percent(row.target_achievement)}</td></tr>)}</tbody></table> : <p className="empty">Chưa có dữ liệu ngày trong bộ lọc.</p>}</div></section>;
}
