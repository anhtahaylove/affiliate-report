"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import { dailyReportExportUrl } from "@/lib/api";
import { AppShell, ConnectionErrorCard, SignInCard } from "@/components/app-shell";
import { FilterBar, useUrlFilters } from "@/components/filters";
import { Notice, canWrite, isOwner } from "@/components/ui";
import { UpdateBanner } from "@/components/update-banner";
import { DashboardFirstRun } from "@/components/pages/dashboard-first-run";
import { ThemePreferences, type Theme } from "@/components/theme-toggle";
import { SavedViews } from "@/components/saved-views";
import { createAccountDirectory } from "@/lib/account-directory";
import { PageHeader } from "@/components/ui-system";
import { useOperationsBootstrap } from "@/components/use-operations-bootstrap";

function RouteLoading() {
  return <section className="panel loading-state" aria-live="polite"><span className="skeleton-line short" /><span className="skeleton-line" /><span className="skeleton-line" /><span className="sr-only">Đang tải nội dung trang…</span></section>;
}

const AnalyticsPage = dynamic(() => import("@/components/pages/analytics").then((module) => module.AnalyticsPage), { loading: RouteLoading, ssr: false });
const DashboardHome = dynamic(() => import("@/components/pages/dashboard").then((module) => module.DashboardHome), { loading: RouteLoading, ssr: false });
const OrdersPage = dynamic(() => import("@/components/pages/orders").then((module) => module.OrdersPage), { loading: RouteLoading, ssr: false });
const ImportsPage = dynamic(() => import("@/components/pages/imports").then((module) => module.ImportsPage), { loading: RouteLoading, ssr: false });
const TargetsPage = dynamic(() => import("@/components/pages/targets").then((module) => module.TargetsPage), { loading: RouteLoading, ssr: false });
const AccountsPage = dynamic(() => import("@/components/pages/accounts").then((module) => module.AccountsPage), { loading: RouteLoading, ssr: false });
const DataSettingsPage = dynamic(() => import("@/components/pages/data-settings").then((module) => module.DataSettingsPage), { loading: RouteLoading, ssr: false });
const AndroidUpdateSettings = dynamic(() => import("@/components/pages/update-settings").then((module) => module.AndroidUpdateSettings), { loading: RouteLoading, ssr: false });
const UpdateSettingsPage = dynamic(() => import("@/components/pages/update-settings").then((module) => module.UpdateSettingsPage), { loading: RouteLoading, ssr: false });
const UsersSettingsPage = dynamic(() => import("@/components/pages/users-settings").then((module) => module.UsersSettingsPage), { loading: RouteLoading, ssr: false });
const SyncSettingsPage = dynamic(() => import("@/components/pages/sync-settings").then((module) => module.SyncSettingsPage), { loading: RouteLoading, ssr: false });

type RouteKind = "dashboard" | "analytics" | "orders" | "imports" | "targets" | "accounts" | "preferences" | "data" | "sync" | "update" | "users";

const routeMeta: Record<RouteKind, { label: string; title: string; copy: string; needsWrite?: boolean; needsOwner?: boolean; filters?: boolean; search?: boolean }> = {
  dashboard: { label: "Tổng quan", title: "Tổng quan hiệu suất", copy: "Theo dõi hoa hồng, tiến độ mục tiêu và phạm vi dữ liệu hiện tại.", filters: true },
  analytics: { label: "Phân tích", title: "Phân tích xu hướng", copy: "Phân tích tài chính, sản phẩm, cửa hàng, nội dung, quyết toán và chất lượng dữ liệu.", filters: true },
  orders: { label: "Đơn hàng", title: "Tra cứu đơn hàng", copy: "Tìm kiếm, lọc và xuất Excel toàn bộ đơn hàng theo phạm vi hiện tại.", filters: true, search: true },
  imports: { label: "Nhập dữ liệu", title: "Nhập tệp TikTok", copy: "Chọn tài khoản TikTok và nhập nhiều tệp Excel tuần tự; hệ thống báo kết quả từng tệp.", needsWrite: true },
  targets: { label: "Mục tiêu", title: "Mục tiêu theo tài khoản", copy: "Điều chỉnh KPI mỗi ngày theo tháng; mục tiêu tháng được hệ thống tự tính.", filters: true },
  accounts: { label: "Tài khoản", title: "Quản lý tài khoản TikTok", copy: "Thêm, sửa, lưu trữ và xóa tài khoản TikTok dùng để nhập dữ liệu.", needsOwner: true },
  preferences: { label: "Giao diện", title: "Giao diện ứng dụng", copy: "Cá nhân hóa chế độ màu và cách hiển thị báo cáo." },
  data: { label: "Dữ liệu", title: "Xóa và khôi phục dữ liệu", copy: "Chỉ chủ sở hữu được thao tác; hệ thống luôn tạo bản sao lưu an toàn trước khi thay đổi.", needsOwner: true },
  sync: { label: "Thiết bị & đồng bộ", title: "Thiết bị & đồng bộ", copy: "Xuất hoặc hợp nhất gói dữ liệu mã hóa giữa máy tính và điện thoại mà không dùng cloud database.", needsOwner: true },
  update: { label: "Cập nhật", title: "Cập nhật ứng dụng", copy: "Kiểm tra nguồn phát hành công khai đã ký và cài đúng gói dành cho thiết bị này.", needsOwner: true },
  users: { label: "Người dùng", title: "Quản lý người dùng", copy: "Phân quyền vai trò và phạm vi tài khoản cho từng người dùng.", needsOwner: true },
};

export function OperationsPage({ route }: { route: RouteKind }) {
  const filters = useUrlFilters();
  const { authError, connectionError, loading, metaData, preferences, refreshAccountMetadata, retry, updatePreferences, user } = useOperationsBootstrap();
  const accountDirectory = useMemo(
    () => createAccountDirectory(metaData?.account_items, metaData?.accounts),
    [metaData],
  );

  if (loading) return <main className="auth-shell"><section className="auth-card panel"><div className="brand-badge">AFF</div><h1>Đang tải trung tâm vận hành…</h1><p className="hint">Đang kiểm tra phiên đăng nhập và kết nối dữ liệu.</p></section></main>;
  if (authError) return <SignInCard message={authError} />;
  if (connectionError || !user) return <ConnectionErrorCard message={connectionError || "Không thể tải cấu hình ứng dụng."} onRetry={retry} />;
  if (!preferences || !metaData) return <ConnectionErrorCard message="Không thể tải cấu hình ứng dụng." onRetry={retry} />;
  const pageMeta = routeMeta[route];
  const shellProps = {
    user,
    appVersion: metaData.app_version ?? "",
    runtimePlatform: metaData.runtime_platform,
    collapsed: preferences.sidebar_collapsed,
    onCollapsedChange: (collapsed: boolean) => updatePreferences({ sidebar_collapsed: collapsed }),
    heading: <PageHeader title={pageMeta.title} description={pageMeta.copy} />,
  };
  if (pageMeta.needsWrite && !canWrite(user)) return <AppShell {...shellProps}><Notice text="Bạn không có quyền nhập dữ liệu. Hãy liên hệ chủ sở hữu để được cấp quyền." /></AppShell>;
  if (pageMeta.needsOwner && !isOwner(user)) return <AppShell {...shellProps}><Notice text="Chỉ chủ sở hữu được truy cập trang này." /></AppShell>;

  return (
    <AppShell {...shellProps}>
      {metaData.runtime_platform !== "android" ? <UpdateBanner capability={metaData.capabilities.update_check} onUpdatePage={route === "update"} /> : null}
      {(["dashboard", "analytics", "orders"] as RouteKind[]).includes(route) ? <SavedViews route={route as "dashboard" | "analytics" | "orders"} /> : null}
      {pageMeta.filters ? <FilterBar accounts={metaData.accounts} directory={accountDirectory} statuses={route === "targets" ? [] : metaData.statuses} showSearch={pageMeta.search} actions={route === "dashboard" ? <a className="button-link secondary-link" download="affiliate-daily-report.xlsx" href={dailyReportExportUrl({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end })}>Xuất báo cáo ngày</a> : null} /> : null}
      {route === "dashboard" ? metaData.accounts.length
        ? <DashboardHome user={user} filters={filters} accounts={metaData.accounts} directory={accountDirectory} preferences={preferences} onPreferencesChange={updatePreferences} />
        : <DashboardFirstRun user={user} setup={{ hasAccounts: false, hasImports: false, hasTarget: false }} />
        : null}
      {route === "analytics" ? <AnalyticsPage filters={filters} directory={accountDirectory} /> : null}
      {route === "orders" ? <OrdersPage filters={filters} directory={accountDirectory} /> : null}
      {route === "imports" ? <ImportsPage user={user} accounts={metaData.accounts} directory={accountDirectory} maxUploadMb={metaData.max_upload_mb} /> : null}
      {route === "targets" ? <TargetsPage user={user} filters={filters} accounts={metaData.accounts} directory={accountDirectory} /> : null}
      {route === "accounts" ? <AccountsPage onAccountsChanged={refreshAccountMetadata} /> : null}
      {route === "preferences" ? <ThemePreferences value={preferences.theme} onChange={(theme: Theme) => updatePreferences({ theme })} /> : null}
      {route === "data" ? <DataSettingsPage capability={metaData.capabilities.data_admin} backend={metaData.capabilities.database_backend} /> : null}
      {route === "sync" ? <SyncSettingsPage capability={metaData.capabilities.sync} backend={metaData.capabilities.database_backend} runtimePlatform={metaData.runtime_platform} /> : null}
      {route === "update" ? metaData.runtime_platform === "android"
        ? <AndroidUpdateSettings capability={metaData.capabilities.android_update} status={metaData.android_update} />
        : <UpdateSettingsPage checkCapability={metaData.capabilities.update_check} installCapability={metaData.capabilities.update_install} /> : null}
      {route === "users" ? <UsersSettingsPage currentUser={user} accounts={metaData.accounts} directory={accountDirectory} identityPolicy={metaData.identity_policy} /> : null}
    </AppShell>
  );
}
