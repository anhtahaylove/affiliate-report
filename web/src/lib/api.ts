export type OverviewRow = {
  account: string;
  orders: number;
  order_lines: number;
  gmv: number;
  units_sold: number;
  cancelled_gmv: number;
  actual_gmv: number;
  actual_commission: number;
  final_received?: number;
};

export type DailyRow = {
  day: string;
  account: string;
  orders: number;
  actual_gmv: number;
  actual_commission: number;
  daily_target: number | null;
  target_achievement: number | null;
};

export type TargetRow = {
  account: string;
  month: string;
  daily_target_commission: number;
  updated_at?: string | null;
  updated_by?: string | null;
};

export type MonthlyKpiRow = {
  month: string;
  account: string;
  daily_target: number | null;
  days_in_scope: number;
  monthly_target: number | null;
  actual_commission: number;
  gap: number | null;
  target_achievement: number | null;
  // "Hiệu suất gộp" — kể cả đơn Không đủ điều kiện. Chỉ để theo dõi sức bán, KHÔNG dùng thay
  // actual_commission/target_achievement khi quyết định đã đạt mục tiêu hay chưa.
  combined_commission: number;
  combined_gap: number | null;
  combined_target_achievement: number | null;
  ineligible_commission: number;
  ineligible_rate: number | null;
  order_lines: number;
};

export type OrderRow = {
  business_key: string;
  account: string;
  order_id: string | null;
  sku_id: string | null;
  product_id: string | null;
  product_name: string | null;
  shop_id: string | null;
  shop_name: string | null;
  content_type: string | null;
  content_id: string | null;
  order_type: string | null;
  commission_type: string | null;
  currency: string | null;
  status: string | null;
  order_date: string | null;
  settlement_date: string | null;
  gmv: number | null;
  actual_gmv: number | null;
  units_sold: number | null;
  units_refunded: number | null;
  estimated_commission: number | null;
  actual_commission: number | null;
  final_received: number | null;
  version: number | null;
  created_at: string | null;
};

export type ImportHistoryRow = {
  id: number;
  filename: string;
  account: string;
  uploaded_by_label: string | null;
  inserted: number;
  updated: number;
  unchanged: number;
  rejected: number;
  created_at: string;
};

export type UndoImportPreview = {
  batch_id: number;
  account: string;
  filename: string;
  created_at: string | null;
  uploaded_by_label: string | null;
  is_latest: boolean;
  newer_batches: number;
  removed_versions: number;
  removed_raw_rows: number;
  removed_lines: number;
  restored_lines: number;
  confirmation: string;
  warning: string | null;
};

export type UndoImportResult = {
  batch_id: number;
  account: string;
  filename: string;
  removed_versions: number;
  removed_raw_rows: number;
  removed_lines: number;
  restored_lines: number;
  backup_path: string | null;
};

export type OrderVersionRow = {
  version: number;
  is_current: boolean;
  account: string;
  order_id: string | null;
  sku_id: string | null;
  status: string | null;
  gmv: number | null;
  units_sold: number | null;
  units_refunded: number | null;
  estimated_commission: number | null;
  final_received: number | null;
  order_date: string | null;
  settlement_date: string | null;
  recorded_at: string | null;
  batch_id: number | null;
  filename: string | null;
  uploaded_by_label: string | null;
};

export type UploadResponse = {
  batch_id?: number | string | null;
  duplicate: boolean;
  inserted: number;
  updated: number;
  unchanged: number;
  rejected: number;
  rejected_rows?: RejectedRow[];
};

export type RejectedRow = {
  row_number: number;
  reason: string;
};

export type ResetDataResponse = {
  backup_path: string;
  deleted_counts: Record<string, number>;
  targets_preserved: boolean;
};

export type BackupItem = {
  id: string;
  filename: string;
  created_at: string;
  size_bytes: number;
  valid: boolean;
  counts: {
    business: Record<string, number>;
    ui?: Record<string, number>;
    auth: Record<string, number>;
  };
  error?: string | null;
};

export type RestoreBackupResponse = {
  restored_counts: Record<string, number>;
  safety_backup_path: string;
};

export type DashboardWidget =
  | "today_pulse"
  | "target_progress"
  | "action_alerts"
  | "trend"
  | "account_contribution"
  | "settlement"
  | "data_freshness"
  | "recent_imports";

export type UiPreferences = {
  theme: "system" | "light" | "dark";
  sidebar_collapsed: boolean;
  dashboard_layout: {
    schema: 1;
    order: DashboardWidget[];
    hidden: DashboardWidget[];
  };
  updated_at?: string | null;
};

export type SavedViewRoute = "dashboard" | "analytics" | "orders";

export type SavedReportView = {
  id: number;
  route: SavedViewRoute;
  name: string;
  filters: Record<string, unknown> & { schema: 1 };
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type UpdateStatus = {
  current_version: string;
  latest_version: string;
  available: boolean;
  installable: boolean;
  automatic_install_supported: boolean;
  release_name: string | null;
  release_url: string | null;
  published_at: string | null;
  notes: string | null;
  source_repo: string | null;
};

export type InstallUpdateResponse = {
  version: string;
  status: string;
  release_url: string;
};

export type UpdateProgressPhase = "idle" | "downloading" | "verifying" | "waiting_for_exit" | "installing" | "restarting" | "installed" | "failed";

export type UpdateProgress = {
  schema: string;
  phase: UpdateProgressPhase;
  current_version: string;
  target_version: string | null;
  bytes_downloaded: number;
  bytes_total: number;
  percent: number | null;
  error: string | null;
  updated_at: string | null;
};

export type MetaResponse = {
  accounts: string[];
  account_items?: AccountItem[];
  statuses: string[];
  max_upload_mb: number;
  app_version?: string;
};

export type UserRole = "viewer" | "operator" | "owner";

export type CurrentUser = {
  email: string;
  role: UserRole;
  accounts?: string[];
  auth_method?: string;
  desktop_app?: boolean;
  desktop_control_token?: string | null;
};

export type AdminUser = {
  id: number;
  email: string;
  display_name?: string | null;
  role: UserRole;
  active: boolean;
  accounts: string[];
};

export type UserPatch = Partial<Pick<AdminUser, "role" | "active" | "accounts">>;

export type AccountItem = {
  code: string;
  display_name: string;
  active: boolean;
  display_order: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type AccountsResponse = ListResponse<AccountItem> & {
  hard_delete_supported: boolean;
};

export type AccountDeletePreview = {
  code: string;
  exists: boolean;
  dependency_counts: Record<string, number>;
  can_hard_delete: boolean;
  postgres_action: string;
  action: "hard_delete" | "archive";
};

export type AccountDeleteResponse = {
  code: string;
  archived: boolean;
  hard_deleted: boolean;
  backup_path?: string;
  account?: AccountItem;
  dependency_counts: Record<string, number>;
};

export type AnalyticsSummary = {
  orders: number;
  order_lines: number;
  gross_gmv: number;
  actual_gmv: number;
  initial_commission: number;
  actual_commission: number;
  final_received: number;
  units_sold: number;
  units_refunded: number;
  effective_commission_rate: number | null;
  refund_rate: number | null;
  ineligible_rate: number | null;
  final_received_variance: number;
  latest_order_date: string | null;
};

export type AnalyticsTrendRow = {
  period: string;
  orders: number;
  order_lines: number;
  gross_gmv: number;
  actual_gmv: number;
  actual_commission: number;
  final_received: number;
};

export type AnalyticsBreakdownRow = {
  orders: number;
  order_lines: number;
  gross_gmv: number;
  initial_commission: number;
  actual_gmv: number;
  actual_commission: number;
  order_share: number;
  gmv_share: number | null;
  commission_share: number | null;
  share: number | null;
  status?: string;
  account?: string;
};

export type AnalyticsDimensionRow = {
  id: string;
  label: string;
  orders: number;
  order_lines: number;
  units_sold: number;
  units_refunded: number;
  gross_gmv: number;
  actual_gmv: number;
  actual_commission: number;
  ineligible_rate: number | null;
  cancelled_orders: number;
  cancellation_rate: number | null;
};

export type AnalyticsResponse = {
  filters: {
    accounts: string[];
    start: string | null;
    end: string | null;
    statuses: string[];
    group_by: "day" | "week" | "month";
    top: number;
  };
  summary: AnalyticsSummary;
  previous_period: { range: { start: string; end: string }; summary: AnalyticsSummary } | null;
  target: {
    monthly_target: number | null;
    actual_commission: number;
    remaining: number | null;
    achievement: number | null;
    elapsed_days: number;
    scope_days: number;
    remaining_days: number;
    required_per_remaining_day: number | null;
    projected_month_end: number | null;
    projected_achievement: number | null;
  } | null;
  trend: AnalyticsTrendRow[];
  status_breakdown: AnalyticsBreakdownRow[];
  account_breakdown: AnalyticsBreakdownRow[];
  products: AnalyticsDimensionRow[];
  shops: AnalyticsDimensionRow[];
  content: AnalyticsDimensionRow[];
  settlement: {
    median_lag_days: number | null;
    settled_lines: number;
    pending_lines: number;
    pending_aging: Array<{ bucket: string; count: number }>;
  };
  data_quality: {
    unknown_status_rows: number;
    non_vnd_rows: number;
    missing_order_date_rows: number;
    missing_settlement_date_rows: number;
    settled_missing_settlement_rows: number;
    negative_settlement_lag_rows: number;
    import_batches: number;
    import_inserted: number;
    import_updated: number;
    import_unchanged: number;
    import_rejected: number;
    latest_import_at: string | null;
  };
};

export const NETWORK_ERROR_MESSAGE =
  "Không kết nối được tới ứng dụng. Nếu bạn vừa chọn Thoát ứng dụng thì hãy mở lại TikTok Affiliate Report từ Desktop hoặc Start Menu, rồi tải lại trang này.";

export class ApiError extends Error {
  public readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export type ListResponse<T> = {
  items: T[];
  count: number;
};

export type PageResponse<T> = ListResponse<T> & {
  total: number;
  limit: number;
  offset: number;
};

function browserOrigin() {
  return typeof window === "undefined" ? "" : window.location.origin;
}

export function apiUrl() {
  return (process.env.NEXT_PUBLIC_API_URL || browserOrigin()).replace(/\/$/, "");
}

function csrfToken() {
  if (typeof document === "undefined") return undefined;
  const names = new Set(["csrf_token", "csrftoken", "XSRF-TOKEN"]);
  for (const part of document.cookie.split(";")) {
    const [name, value] = part.trim().split("=", 2);
    if (names.has(name)) return value;
  }
  return undefined;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(init?.method?.toUpperCase() ?? "GET")) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  }

  let response: Response;
  try {
    response = await fetch(`${apiUrl()}${path}`, { ...init, credentials: "include", headers });
  } catch {
    // fetch chỉ ném khi không nối được tới server. Với app desktop này, lý do thường gặp nhất là
    // người dùng đã Thoát ứng dụng từ tray mà tab trình duyệt vẫn còn mở. "Failed to fetch" của
    // trình duyệt không nói được điều đó, nên thay bằng câu chỉ đúng việc cần làm.
    throw new ApiError(NETWORK_ERROR_MESSAGE, 0);
  }
  if (!response.ok) {
    let message = `API trả về HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail) message = payload.detail;
    } catch {
      // Keep HTTP fallback.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export function queryString(params: Record<string, string | string[] | number | undefined | null>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (Array.isArray(value)) value.filter(Boolean).forEach((item) => query.append(key, item));
    else if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

export type ReportFilters = {
  accounts?: string[];
  statuses?: string[];
  start?: string;
  end?: string;
  month?: string;
};

function reportQuery(filters: ReportFilters & { search?: string; limit?: number; offset?: number; sort?: string; direction?: string } = {}) {
  return queryString({
    account: filters.accounts,
    status: filters.statuses,
    start: filters.start,
    end: filters.end,
    month: filters.month,
    search: filters.search,
    limit: filters.limit,
    offset: filters.offset,
    sort: filters.sort,
    direction: filters.direction,
  });
}

export async function loadCurrentUser() {
  return request<CurrentUser>("/auth/me");
}

export async function logout() {
  return request<Record<string, unknown>>("/auth/logout", { method: "POST" });
}

export async function exitApplication(controlToken: string) {
  return request<{ status: string }>("/api/v1/admin/shutdown", {
    method: "POST",
    headers: { "X-Desktop-Control-Token": controlToken },
  });
}

export async function loadMeta() {
  return request<MetaResponse>("/api/v1/meta");
}

export async function loadUiPreferences() {
  return request<UiPreferences>("/api/v1/ui/preferences");
}

export async function saveUiPreferences(changes: Partial<Pick<UiPreferences, "theme" | "sidebar_collapsed" | "dashboard_layout">>) {
  return request<UiPreferences>("/api/v1/ui/preferences", {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export async function loadSavedViews(route: SavedViewRoute) {
  return request<ListResponse<SavedReportView>>(`/api/v1/ui/saved-views?route=${encodeURIComponent(route)}`);
}

export async function createSavedView(changes: { route: SavedViewRoute; name: string; filters: Record<string, unknown>; is_default?: boolean }) {
  return request<SavedReportView>("/api/v1/ui/saved-views", {
    method: "POST",
    body: JSON.stringify(changes),
  });
}

export async function updateSavedView(viewId: number, changes: { name?: string; filters?: Record<string, unknown>; is_default?: boolean }) {
  return request<SavedReportView>(`/api/v1/ui/saved-views/${viewId}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export async function deleteSavedView(viewId: number) {
  return request<{ deleted: boolean }>(`/api/v1/ui/saved-views/${viewId}`, { method: "DELETE" });
}

export async function loadAccounts() {
  return request<AccountsResponse>("/api/v1/accounts");
}

export async function createAccount(changes: { code: string; display_name: string; display_order?: number | null }) {
  return request<AccountItem>("/api/v1/accounts", {
    method: "POST",
    body: JSON.stringify(changes),
  });
}

export async function updateAccount(code: string, changes: { display_name?: string; display_order?: number | null; active?: boolean }) {
  return request<AccountItem>(`/api/v1/accounts/${encodeURIComponent(code)}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export async function previewDeleteAccount(code: string) {
  return request<AccountDeletePreview>(`/api/v1/accounts/${encodeURIComponent(code)}/delete-preview`);
}

export async function deleteAccount(code: string, confirmation: string) {
  return request<AccountDeleteResponse>(`/api/v1/accounts/${encodeURIComponent(code)}`, {
    method: "DELETE",
    body: JSON.stringify({ confirmation }),
  });
}

export async function loadDashboard(filters: ReportFilters) {
  const query = reportQuery(filters);
  const [overview, daily] = await Promise.all([
    request<ListResponse<OverviewRow>>(`/api/v1/overview${query}`),
    request<ListResponse<DailyRow>>(`/api/v1/daily${query}`),
  ]);
  return { overview: overview.items, daily: daily.items };
}

export async function loadAnalytics(filters: ReportFilters) {
  return request<AnalyticsResponse>(`/api/v1/analytics${reportQuery(filters)}`);
}

export async function loadOrders(filters: ReportFilters & { search?: string; limit?: number; offset?: number; sort?: string; direction?: "asc" | "desc" }) {
  return request<PageResponse<OrderRow>>(`/api/v1/orders${reportQuery(filters)}`);
}

export function ordersExportUrl(filters: ReportFilters & { search?: string }) {
  return `${apiUrl()}/api/v1/orders/export.xlsx${reportQuery(filters)}`;
}

export function dailyReportExportUrl(filters: ReportFilters) {
  return `${apiUrl()}/api/v1/reports/daily.xlsx${queryString({
    account: filters.accounts,
    status: filters.statuses,
    start: filters.start,
    end: filters.end,
  })}`;
}

export function visibleRejectedRows(rows: RejectedRow[] = []) {
  return rows.slice(0, 10);
}

export async function loadMonthlyKpi(filters: ReportFilters) {
  return request<ListResponse<MonthlyKpiRow>>(`/api/v1/monthly-kpi${reportQuery(filters)}`);
}

export async function loadTargets(month: string, accounts?: string[]) {
  return request<ListResponse<TargetRow>>(`/api/v1/targets${queryString({ month, account: accounts })}`);
}

export async function saveTarget(account: string, month: string, targetCommission: number) {
  return request<TargetRow>(`/api/v1/targets/${encodeURIComponent(account)}/${month}`, {
    method: "PUT",
    body: JSON.stringify({ daily_target_commission: targetCommission }),
  });
}

export type CopyTargetsResponse = {
  month: string;
  from_month: string;
  copied: Array<{ account: string; daily_target_commission: number }>;
  kept: string[];
};

export async function copyPreviousTargets(month: string) {
  return request<CopyTargetsResponse>(`/api/v1/targets/${month}/copy-previous`, { method: "POST" });
}

export async function loadImportHistory(limit = 10, accounts?: string[]) {
  return request<ListResponse<ImportHistoryRow> & { limit: number }>(`/api/v1/imports${queryString({ limit, account: accounts })}`);
}

export async function previewUndoImport(batchId: number) {
  return request<UndoImportPreview>(`/api/v1/imports/${batchId}/undo-preview`);
}

export async function undoImport(batchId: number, confirmation: string) {
  return request<UndoImportResult>(`/api/v1/imports/${batchId}`, {
    method: "DELETE",
    body: JSON.stringify({ confirmation }),
  });
}

export async function loadOrderVersions(businessKey: string) {
  return request<ListResponse<OrderVersionRow>>(`/api/v1/orders/${encodeURIComponent(businessKey)}/versions`);
}

export async function resetData(confirmation: string) {
  return request<ResetDataResponse>("/api/v1/admin/reset-data", {
    method: "POST",
    body: JSON.stringify({ confirmation }),
  });
}

export async function loadBackups() {
  return request<ListResponse<BackupItem>>("/api/v1/admin/backups");
}

export async function previewBackup(backupId: string) {
  return request<BackupItem>(`/api/v1/admin/backups/${encodeURIComponent(backupId)}/preview`);
}

export async function restoreBackup(backupId: string, confirmation: string) {
  return request<RestoreBackupResponse>("/api/v1/admin/backups/restore", {
    method: "POST",
    body: JSON.stringify({ backup_id: backupId, confirmation }),
  });
}

export async function checkUpdate() {
  return request<UpdateStatus>("/api/v1/admin/update");
}

export async function installUpdate(confirmation: string) {
  return request<InstallUpdateResponse>("/api/v1/admin/update/install", {
    method: "POST",
    body: JSON.stringify({ confirmation }),
  });
}

export async function loadUpdateProgress() {
  return request<UpdateProgress>("/api/v1/admin/update/progress");
}

export async function loadUsers() {
  return request<ListResponse<AdminUser>>("/api/v1/admin/users");
}

export async function updateUser(userId: number, changes: UserPatch) {
  return request<AdminUser>(`/api/v1/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export async function uploadExport(account: string, file: File) {
  const body = new FormData();
  body.set("account", account);
  body.set("file", file);
  return request<UploadResponse>("/api/v1/imports", { method: "POST", body });
}
