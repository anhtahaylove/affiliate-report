export type OverviewRow = {
  account: string;
  orders: number;
  order_lines: number;
  gmv: number;
  units_sold: number;
  cancelled_gmv: number;
  actual_gmv: number;
  actual_commission: number;
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
  target_commission: number;
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
  order_lines: number;
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

export type MetaResponse = {
  accounts: string[];
  statuses: string[];
  max_upload_mb: number;
};

export type UserRole = "viewer" | "operator" | "owner";

export type CurrentUser = {
  email: string;
  role: UserRole;
  accounts?: string[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

type ListResponse<T> = {
  items: T[];
  count: number;
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
  if (init?.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(init?.method?.toUpperCase() ?? "GET")) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  }

  const response = await fetch(`${apiUrl()}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    let message = `API trả về HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail) message = payload.detail;
    } catch {
      // Keep the HTTP fallback when the server did not return JSON.
    }
    throw new ApiError(message, response.status);
  }

  return response.json() as Promise<T>;
}

function queryString(params: Record<string, string | string[] | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => query.append(key, item));
    } else if (value) {
      query.set(key, value);
    }
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

export async function loadCurrentUser() {
  return request<CurrentUser>("/auth/me");
}

export async function logout() {
  return request<Record<string, unknown>>("/auth/logout", { method: "POST" });
}

export async function loadMeta() {
  return request<MetaResponse>("/api/v1/meta");
}

export async function loadDashboard(filters: {
  accounts?: string[];
  start?: string;
  end?: string;
}) {
  const query = queryString({
    account: filters.accounts,
    start: filters.start,
    end: filters.end,
  });
  const [overview, daily] = await Promise.all([
    request<ListResponse<OverviewRow>>(`/api/v1/overview${query}`),
    request<ListResponse<DailyRow>>(`/api/v1/daily${query}`),
  ]);
  return { overview: overview.items, daily: daily.items };
}

export async function loadMonthlyKpi(filters: {
  month?: string;
  accounts?: string[];
  start?: string;
  end?: string;
}) {
  const query = queryString({
    month: filters.month,
    account: filters.accounts,
    start: filters.start,
    end: filters.end,
  });
  return request<ListResponse<MonthlyKpiRow>>(`/api/v1/monthly-kpi${query}`);
}

export async function loadTargets(month: string) {
  const query = queryString({ month });
  return request<ListResponse<TargetRow>>(`/api/v1/targets${query}`);
}

export async function saveTarget(account: string, month: string, targetCommission: number) {
  return request<TargetRow>(`/api/v1/targets/${encodeURIComponent(account)}/${month}`, {
    method: "PUT",
    body: JSON.stringify({ target_commission: targetCommission }),
  });
}

export async function loadImportHistory(limit = 5) {
  const query = queryString({ limit: String(limit) });
  return request<ListResponse<ImportHistoryRow>>(`/api/v1/imports${query}`);
}

export async function uploadExport(account: string, file: File) {
  const body = new FormData();
  body.set("account", account);
  body.set("file", file);
  return request<Record<string, unknown>>("/api/v1/imports", {
    method: "POST",
    body,
  });
}
