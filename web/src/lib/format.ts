export const money = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });
export const integer = new Intl.NumberFormat("vi-VN");
export const dateTime = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const STATUS_LABELS: Record<string, string> = {
  settled: "Đã quyết toán",
  pending: "Đang chờ quyết toán",
  ineligible: "Không đủ điều kiện",
  unknown: "Chưa xác định",
};

const ROLE_LABELS: Record<string, string> = {
  owner: "Chủ sở hữu",
  operator: "Nhân viên vận hành",
  viewer: "Chỉ xem",
};

export function formatMoney(value: number | null | undefined) {
  return value == null || Number.isNaN(Number(value)) ? "—" : money.format(Number(value));
}

export function percent(value: number | null | undefined) {
  return value == null || Number.isNaN(Number(value)) ? "—" : `${(Number(value) * 100).toFixed(1)}%`;
}

export type AchievementTone = "good" | "warning" | "critical" | "neutral";

/** Traffic-light tone for a target-achievement ratio (0–1+), reusing the app's existing status colors. */
export function achievementTone(value: number | null | undefined): AchievementTone {
  if (value == null || Number.isNaN(Number(value))) return "neutral";
  const ratio = Number(value);
  if (ratio >= 1) return "good";
  if (ratio >= 0.5) return "warning";
  return "critical";
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateTime.format(parsed);
}

export function statusLabel(value: string | null | undefined) {
  if (!value) return STATUS_LABELS.unknown;
  return STATUS_LABELS[value.trim().toLowerCase()] ?? value;
}

export function roleLabel(value: string | null | undefined) {
  if (!value) return "Chưa xác định";
  return ROLE_LABELS[value.trim().toLowerCase()] ?? value;
}

const BACKEND_LABELS: Record<string, string> = {
  sqlite: "Lưu trên máy (SQLite)",
  postgresql: "Máy chủ dùng chung (PostgreSQL)",
};

export function backendLabel(value: string | null | undefined) {
  if (!value) return "Chưa xác định";
  return BACKEND_LABELS[value.trim().toLowerCase()] ?? value;
}

export function formatBytes(value: number | null | undefined) {
  if (value == null) return "—";
  if (value < 1024 * 1024) return `${integer.format(Math.max(1, Math.round(value / 1024)))} KB`;
  return `${integer.format(Math.round((value / 1024 / 1024) * 10) / 10)} MB`;
}

export function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function firstDayOfMonth(month: string) {
  return `${month}-01`;
}

export function lastDayOfMonth(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const lastDay = new Date(year, monthNumber, 0).getDate();
  return `${month}-${String(lastDay).padStart(2, "0")}`;
}

function isoDay(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

export function previousMonth() {
  const now = new Date();
  const previous = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, "0")}`;
}

/** Khoảng nhanh: n ngày gần nhất tính cả hôm nay. Tháng báo cáo bám theo ngày cuối khoảng. */
export function lastDays(days: number) {
  const end = new Date();
  const start = new Date(end.getFullYear(), end.getMonth(), end.getDate() - (days - 1));
  return { start: isoDay(start), end: isoDay(end), month: currentMonth() };
}

export function wholeMonth(month: string) {
  return { start: firstDayOfMonth(month), end: lastDayOfMonth(month), month };
}

// Khoá là tên bảng SQL thật (xem accounts._dependency_counts, reset_data._table_counts) — thiếu
// khoá nào thì countsText() rơi xuống in thẳng tên bảng đó (vd. "raw_import_rows: 15000") thay vì
// nhãn tiếng Việt, đúng lúc người dùng cần đọc rõ nhất (xem trước khi xoá tài khoản/dữ liệu).
const COUNT_LABELS: Record<string, string> = {
  accounts: "Tài khoản",
  targets: "Mục tiêu",
  monthly_targets: "Mục tiêu",
  import_batches: "Lượt nhập",
  imports: "Lượt nhập",
  raw_rows: "Dòng dữ liệu gốc",
  raw_import_rows: "Dòng dữ liệu gốc",
  rows: "Dòng dữ liệu",
  tombstones: "Bản ghi đã xóa",
  sync_tombstones: "Bản ghi đã xóa",
  sync_history: "Lượt đồng bộ",
  order_line_versions: "Phiên bản đơn hàng",
  user_account_access: "Phân quyền tài khoản",
  app_users: "Người dùng",
  auth_sessions: "Phiên đăng nhập",
  oidc_login_states: "Yêu cầu đăng nhập đang chờ",
  user_ui_preferences: "Tùy chọn giao diện",
  saved_report_views: "Bộ lọc đã lưu",
};

// Khoá "aging bucket" thô từ reports.py — chưa dịch thì lộ nguyên "0-7"/"31+"/"unknown" ra UI.
const AGING_BUCKET_LABELS: Record<string, string> = {
  "0-7": "0–7 ngày",
  "8-14": "8–14 ngày",
  "15-30": "15–30 ngày",
  "31+": "Trên 31 ngày",
  unknown: "Chưa xác định",
};

export function agingBucketLabel(bucket: string) {
  return AGING_BUCKET_LABELS[bucket] ?? bucket;
}

export function countsText(counts: Record<string, number> | undefined) {
  const entries = Object.entries(counts ?? {});
  return entries.length ? entries.map(([name, count]) => `${COUNT_LABELS[name] ?? name}: ${integer.format(Number(count))}`).join(" · ") : "Không có bảng";
}

// Chỉ tin message khi lỗi có field "status" (chữ ký riêng của ApiError ở api.ts — network error
// hoặc response.detail đã dịch tiếng Việt sẵn). Không import ApiError trực tiếp để format.ts giữ
// nguyên zero-dependency, chạy được qua `node --test` không cần bundler/alias resolver. Error khác
// (TypeError, lỗi render...) không phải lỗi nghiệp vụ đã dịch — message của nó là tiếng Anh/kỹ
// thuật, phải dùng fallback thay vì hiện thẳng cho người dùng không chuyên.
export function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error && "status" in reason && typeof reason.status === "number" ? reason.message : fallback;
}
