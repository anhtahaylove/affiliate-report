"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AnalyticsBreakdownRow, AnalyticsTrendRow } from "@/lib/api";
import { formatMoney, statusLabel } from "@/lib/format";
import type { AccountDirectory } from "@/lib/account-directory";

// Intl.NumberFormat({notation: "compact"}) tự rút "tỷ" xuống còn đúng một chữ "T" — cách chữ
// "Tr" (triệu) đúng một ký tự, cỡ chữ trục chỉ 11-12px nên rất dễ đọc nhầm 1,2 triệu thành 1,2
// tỷ (sai 1000 lần) trên đúng dữ liệu tiền hoa hồng thật. Viết tay để giữ "Tỷ" đủ chữ, phân biệt
// rõ với "Tr".
function compactMoneyTick(value: number): string {
  const abs = Math.abs(value);
  const scaled = (divisor: number) => (value / divisor).toLocaleString("vi-VN", { maximumFractionDigits: 1 });
  if (abs >= 1_000_000_000) return `${scaled(1_000_000_000)} Tỷ`;
  if (abs >= 1_000_000) return `${scaled(1_000_000)} Tr`;
  if (abs >= 1_000) return `${scaled(1_000)} N`;
  return String(Math.round(value));
}

const tooltipStyle = {
  background: "var(--surface-raised)",
  border: "1px solid var(--border-strong)",
  borderRadius: 12,
  color: "var(--text-primary)",
  boxShadow: "var(--shadow-popover)",
};

export function CommissionTrendChart({ rows }: { rows: AnalyticsTrendRow[] }) {
  const data = rows.slice(-30);
  return (
    <div className="ci-chart" role="img" aria-label="Biểu đồ xu hướng hoa hồng thực tế và tiền đã nhận">
      <ResponsiveContainer width="100%" height={286}>
        <AreaChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 4 }} accessibilityLayer>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="period" tickLine={false} axisLine={false} minTickGap={28} tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
          <YAxis tickFormatter={(value) => compactMoneyTick(Number(value))} tickLine={false} axisLine={false} width={56} tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
          <Tooltip contentStyle={tooltipStyle} formatter={(value, name) => [formatMoney(Number(value)), name === "actual_commission" ? "Hoa hồng" : "Đã nhận"]} labelStyle={{ color: "var(--text-primary)" }} />
          <Area type="monotone" dataKey="actual_commission" name="Hoa hồng thực tế" stroke="var(--chart-cyan)" fill="var(--chart-cyan-soft)" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
          <Area type="monotone" dataKey="final_received" name="Đã nhận" stroke="var(--chart-lime)" fill="transparent" strokeWidth={2} dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AccountContributionChart({ rows, directory }: { rows: AnalyticsBreakdownRow[]; directory: AccountDirectory }) {
  const data = rows
    .filter((row) => row.account)
    .slice(0, 8)
    .map((row) => ({ ...row, label: directory.label(row.account) }));
  return (
    <div className="ci-chart" role="img" aria-label="Biểu đồ đóng góp hoa hồng theo tài khoản">
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 46)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }} accessibilityLayer>
          <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
          <XAxis type="number" tickFormatter={(value) => compactMoneyTick(Number(value))} tickLine={false} axisLine={false} tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
          <YAxis dataKey="label" type="category" width={96} tickLine={false} axisLine={false} tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
          <Tooltip contentStyle={tooltipStyle} formatter={(value) => [formatMoney(Number(value)), "Hoa hồng thực tế"]} />
          <Bar dataKey="actual_commission" fill="var(--chart-cyan)" radius={[0, 7, 7, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const statusColors = [
  "var(--chart-lime)",
  "var(--chart-amber)",
  "var(--chart-coral)",
  "var(--chart-cyan)",
  "var(--chart-neutral)",
];

export function StatusMixChart({ rows }: { rows: AnalyticsBreakdownRow[] }) {
  const data = rows.filter((row) => row.status).slice(0, 8).map((row) => ({ ...row, label: statusLabel(row.status) }));
  return (
    <div className="ci-chart" role="img" aria-label="Biểu đồ quy mô GMV theo trạng thái đơn hàng">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }} accessibilityLayer>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
          <YAxis tickFormatter={(value) => compactMoneyTick(Number(value))} tickLine={false} axisLine={false} width={54} tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
          <Tooltip contentStyle={tooltipStyle} formatter={(value) => [formatMoney(Number(value)), "GMV"]} />
          <Bar dataKey="gross_gmv" radius={[7, 7, 0, 0]} isAnimationActive={false}>
            {data.map((row, index) => <Cell key={row.status ?? index} fill={statusColors[index % statusColors.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
