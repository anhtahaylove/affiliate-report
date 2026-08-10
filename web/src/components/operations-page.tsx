"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ApiError, CurrentUser, loadCurrentUser, loadMeta } from "@/lib/api";
import { AppShell, AuthCard } from "@/components/app-shell";
import { FilterBar, useUrlFilters } from "@/components/filters";
import { Notice, canWrite, isOwner } from "@/components/ui";
import { DashboardHome } from "@/components/pages/dashboard";
import { AnalyticsPage } from "@/components/pages/analytics";
import { OrdersPage } from "@/components/pages/orders";
import { ImportsPage } from "@/components/pages/imports";
import { TargetsPage } from "@/components/pages/targets";
import { AccountsPage } from "@/components/pages/accounts";
import { DataSettingsPage } from "@/components/pages/data-settings";
import { UpdateSettingsPage } from "@/components/pages/update-settings";
import { UsersSettingsPage } from "@/components/pages/users-settings";
import { errorMessage } from "@/lib/format";

type RouteKind = "dashboard" | "analytics" | "orders" | "imports" | "targets" | "accounts" | "data" | "update" | "users";

const routeMeta: Record<RouteKind, { label: string; title: string; copy: string; needsWrite?: boolean; needsOwner?: boolean; filters?: boolean; search?: boolean; filterHint?: string }> = {
  dashboard: { label: "Tổng quan", title: "Tổng quan hiệu suất", copy: "Theo dõi hoa hồng, tiến độ mục tiêu và phạm vi dữ liệu hiện tại.", filters: true, filterHint: "Bộ lọc áp dụng cho toàn bộ số liệu và bảng biểu trên trang này." },
  analytics: { label: "Phân tích", title: "Phân tích xu hướng", copy: "Phân tích tài chính, sản phẩm, cửa hàng, nội dung, quyết toán và chất lượng dữ liệu.", filters: true, filterHint: "Bộ lọc áp dụng cho toàn bộ phân tích, xu hướng và xếp hạng bên dưới." },
  orders: { label: "Đơn hàng", title: "Tra cứu đơn hàng", copy: "Tìm kiếm, lọc và xuất Excel toàn bộ đơn hàng theo phạm vi hiện tại.", filters: true, search: true, filterHint: "Bộ lọc áp dụng trực tiếp cho danh sách đơn hàng và các file xuất." },
  imports: { label: "Nhập dữ liệu", title: "Nhập file TikTok", copy: "Chọn tài khoản TikTok và nhập nhiều file Excel tuần tự; hệ thống báo kết quả từng file.", needsWrite: true },
  targets: { label: "Mục tiêu", title: "Mục tiêu theo tài khoản", copy: "Điều chỉnh KPI mỗi ngày theo tháng; mục tiêu tháng được hệ thống tự tính.", filters: true, filterHint: "Bộ lọc áp dụng cho phạm vi KPI hiển thị; mục tiêu vẫn được lưu riêng theo từng tài khoản." },
  accounts: { label: "Tài khoản", title: "Quản lý tài khoản TikTok", copy: "Thêm, sửa, lưu trữ và xóa tài khoản TikTok dùng để nhập dữ liệu.", needsOwner: true },
  data: { label: "Dữ liệu", title: "Xóa và khôi phục dữ liệu", copy: "Chỉ chủ sở hữu được thao tác; hệ thống luôn tạo bản sao lưu an toàn trước khi thay đổi.", needsOwner: true },
  update: { label: "Cập nhật", title: "Cập nhật ứng dụng", copy: "Kiểm tra nguồn cập nhật công khai đã ký và cài phiên bản mới trong ứng dụng Windows.", needsOwner: true },
  users: { label: "Người dùng", title: "Quản lý người dùng", copy: "Phân quyền vai trò và phạm vi tài khoản cho từng người dùng.", needsOwner: true },
};

const settingsTabs: Array<{ href: string; label: string }> = [
  { href: "/settings/data", label: "Dữ liệu" },
  { href: "/settings/update", label: "Cập nhật" },
  { href: "/settings/users", label: "Người dùng" },
];

function SettingsTabs() {
  const pathname = usePathname();
  return (
    <nav className="settings-tabs" aria-label="Mục cài đặt">
      {settingsTabs.map((tab) => (
        <Link key={tab.href} href={tab.href} className={pathname === tab.href ? "active" : undefined} aria-current={pathname === tab.href ? "page" : undefined}>
          {tab.label}
        </Link>
      ))}
    </nav>
  );
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
      {["data", "update", "users"].includes(route) ? <SettingsTabs /> : null}
      {meta.filters ? <><FilterBar accounts={accounts} statuses={route === "targets" ? [] : statuses} showSearch={meta.search} />{meta.filterHint ? <p className="hint">{meta.filterHint}</p> : null}</> : null}
      {route === "dashboard" ? <DashboardHome filters={filters} accounts={accounts} /> : null}
      {route === "analytics" ? <AnalyticsPage filters={filters} /> : null}
      {route === "orders" ? <OrdersPage filters={filters} /> : null}
      {route === "imports" ? <ImportsPage user={user} accounts={accounts} maxUploadMb={maxUploadMb} /> : null}
      {route === "targets" ? <TargetsPage user={user} filters={filters} accounts={accounts} /> : null}
      {route === "accounts" ? <AccountsPage /> : null}
      {route === "data" ? <DataSettingsPage /> : null}
      {route === "update" ? <UpdateSettingsPage /> : null}
      {route === "users" ? <UsersSettingsPage currentUser={user} accounts={accounts} /> : null}
    </AppShell>
  );
}
