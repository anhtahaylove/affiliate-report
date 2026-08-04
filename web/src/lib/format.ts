export const money = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });
export const integer = new Intl.NumberFormat("vi-VN");
export const dateTime = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });

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

export function accountLabel(value: string | null | undefined) {
  return value === "ALL" ? "Tất cả tài khoản" : value || "Chưa xác định";
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

export function countsText(counts: Record<string, number> | undefined) {
  const entries = Object.entries(counts ?? {});
  return entries.length ? entries.map(([name, count]) => `${name}: ${integer.format(Number(count))}`).join(" · ") : "Không có bảng";
}

export function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}
