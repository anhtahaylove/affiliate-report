"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ApiError, CurrentUser, dailyReportExportUrl, loadCurrentUser, loadMeta, loadUiPreferences, saveUiPreferences, type IdentityPolicy, type RuntimeCapabilities, type UiPreferences } from "@/lib/api";
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
import { applyThemePreference, ThemePreferences, type Theme } from "@/components/theme-toggle";
import { errorMessage } from "@/lib/format";
import { SavedViews } from "@/components/saved-views";
import { routeIsActive } from "@/lib/navigation";

type RouteKind = "dashboard" | "analytics" | "orders" | "imports" | "targets" | "accounts" | "preferences" | "data" | "update" | "users";

const routeMeta: Record<RouteKind, { label: string; title: string; copy: string; needsWrite?: boolean; needsOwner?: boolean; filters?: boolean; search?: boolean }> = {
  dashboard: { label: "Tổng quan", title: "Tổng quan hiệu suất", copy: "Theo dõi hoa hồng, tiến độ mục tiêu và phạm vi dữ liệu hiện tại.", filters: true },
  analytics: { label: "Phân tích", title: "Phân tích xu hướng", copy: "Phân tích tài chính, sản phẩm, cửa hàng, nội dung, quyết toán và chất lượng dữ liệu.", filters: true },
  orders: { label: "Đơn hàng", title: "Tra cứu đơn hàng", copy: "Tìm kiếm, lọc và xuất Excel toàn bộ đơn hàng theo phạm vi hiện tại.", filters: true, search: true },
  imports: { label: "Nhập dữ liệu", title: "Nhập tệp TikTok", copy: "Chọn tài khoản TikTok và nhập nhiều tệp Excel tuần tự; hệ thống báo kết quả từng tệp.", needsWrite: true },
  targets: { label: "Mục tiêu", title: "Mục tiêu theo tài khoản", copy: "Điều chỉnh KPI mỗi ngày theo tháng; mục tiêu tháng được hệ thống tự tính.", filters: true },
  accounts: { label: "Tài khoản", title: "Quản lý tài khoản TikTok", copy: "Thêm, sửa, lưu trữ và xóa tài khoản TikTok dùng để nhập dữ liệu.", needsOwner: true },
  preferences: { label: "Giao diện", title: "Giao diện ứng dụng", copy: "Cá nhân hóa chế độ màu và cách hiển thị báo cáo." },
  data: { label: "Dữ liệu", title: "Xóa và khôi phục dữ liệu", copy: "Chỉ chủ sở hữu được thao tác; hệ thống luôn tạo bản sao lưu an toàn trước khi thay đổi.", needsOwner: true },
  update: { label: "Cập nhật", title: "Cập nhật ứng dụng", copy: "Kiểm tra nguồn cập nhật công khai đã ký và cài phiên bản mới trong ứng dụng Windows.", needsOwner: true },
  users: { label: "Người dùng", title: "Quản lý người dùng", copy: "Phân quyền vai trò và phạm vi tài khoản cho từng người dùng.", needsOwner: true },
};

const settingsTabs: Array<{ href: string; label: string }> = [
  { href: "/settings/preferences", label: "Giao diện" },
  { href: "/settings/data", label: "Dữ liệu" },
  { href: "/settings/update", label: "Cập nhật" },
  { href: "/settings/users", label: "Người dùng" },
];

function SettingsTabs({ user }: { user: CurrentUser }) {
  const pathname = usePathname();
  const visibleTabs = isOwner(user) ? settingsTabs : settingsTabs.slice(0, 1);
  return (
    <nav className="settings-tabs" aria-label="Mục cài đặt">
      {visibleTabs.map((tab) => (
        <Link key={tab.href} href={tab.href} className={routeIsActive(pathname, tab.href) ? "active" : undefined} aria-current={routeIsActive(pathname, tab.href) ? "page" : undefined}>
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
  const [appVersion, setAppVersion] = useState("");
  const [capabilities, setCapabilities] = useState<RuntimeCapabilities | null>(null);
  const [identityPolicy, setIdentityPolicy] = useState<IdentityPolicy | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");
  const [authError, setAuthError] = useState("");
  const [preferences, setPreferences] = useState<UiPreferences | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [currentUser, meta, uiPreferences] = await Promise.all([loadCurrentUser(), loadMeta(), loadUiPreferences()]);
        if (!active) return;
        setUser(currentUser);
        setAccounts(meta.accounts);
        setStatuses(meta.statuses);
        setMaxUploadMb(meta.max_upload_mb);
        setAppVersion(meta.app_version ?? "");
        setCapabilities(meta.capabilities);
        setIdentityPolicy(meta.identity_policy);
        setPreferences(uiPreferences);
        applyThemePreference(uiPreferences.theme);
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
  if (!preferences || !capabilities || !identityPolicy) return <AuthCard message="Không thể tải cấu hình ứng dụng." />;
  const meta = routeMeta[route];
  async function updatePreferences(changes: Partial<Pick<UiPreferences, "theme" | "sidebar_collapsed" | "dashboard_layout">>) {
    const updated = await saveUiPreferences(changes);
    setPreferences(updated);
    applyThemePreference(updated.theme);
  }
  const shellProps = { user, apiError, appVersion, collapsed: preferences.sidebar_collapsed, onCollapsedChange: (collapsed: boolean) => updatePreferences({ sidebar_collapsed: collapsed }) };
  if (meta.needsWrite && !canWrite(user)) return <AppShell {...shellProps}><Notice text="Bạn không có quyền nhập dữ liệu. Hãy liên hệ chủ sở hữu để được cấp quyền." /></AppShell>;
  if (meta.needsOwner && !isOwner(user)) return <AppShell {...shellProps}><Notice text="Chỉ chủ sở hữu được truy cập trang này." /></AppShell>;

  return (
    <AppShell {...shellProps} heading={<div className="page-heading"><h1>{meta.title}</h1><p className="subtle">{meta.copy}</p></div>}>
      {["preferences", "data", "update", "users"].includes(route) ? <SettingsTabs user={user} /> : null}
      {(["dashboard", "analytics", "orders"] as RouteKind[]).includes(route) ? <SavedViews route={route as "dashboard" | "analytics" | "orders"} /> : null}
      {meta.filters ? <FilterBar accounts={accounts} statuses={route === "targets" ? [] : statuses} showSearch={meta.search} actions={route === "dashboard" ? <a className="button-link secondary-link" download="tiktok-affiliate-daily-report.xlsx" href={dailyReportExportUrl({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end })}>Xuất báo cáo ngày</a> : null} /> : null}
      {route === "dashboard" ? <DashboardHome filters={filters} accounts={accounts} preferences={preferences} onPreferencesChange={updatePreferences} /> : null}
      {route === "analytics" ? <AnalyticsPage filters={filters} /> : null}
      {route === "orders" ? <OrdersPage filters={filters} /> : null}
      {route === "imports" ? <ImportsPage user={user} accounts={accounts} maxUploadMb={maxUploadMb} /> : null}
      {route === "targets" ? <TargetsPage user={user} filters={filters} accounts={accounts} /> : null}
      {route === "accounts" ? <AccountsPage /> : null}
      {route === "preferences" ? <ThemePreferences value={preferences.theme} onChange={(theme: Theme) => updatePreferences({ theme })} /> : null}
      {route === "data" ? <DataSettingsPage capability={capabilities.data_admin} backend={capabilities.database_backend} /> : null}
      {route === "update" ? <UpdateSettingsPage checkCapability={capabilities.update_check} installCapability={capabilities.update_install} /> : null}
      {route === "users" ? <UsersSettingsPage currentUser={user} accounts={accounts} identityPolicy={identityPolicy} /> : null}
    </AppShell>
  );
}
