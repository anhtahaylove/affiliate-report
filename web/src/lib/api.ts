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

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

function csrfToken() {
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
  if (!["GET", "HEAD", "OPTIONS"].includes(init?.method?.toUpperCase() ?? "GET")) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(detail || `API trả về HTTP ${response.status}`, response.status);
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

export async function uploadExport(account: string, file: File) {
  const body = new FormData();
  body.set("account", account);
  body.set("file", file);
  return request<Record<string, unknown>>("/api/v1/imports", {
    method: "POST",
    body,
  });
}
