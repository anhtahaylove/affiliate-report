"use client";

import { lazy, Suspense, useMemo } from "react";
import { AppShell, ConnectionErrorCard, SignInCard } from "@/components/app-shell";
import { DashboardFirstRun } from "@/components/pages/dashboard-first-run";
import { FilterBar, useUrlFilters } from "@/components/filters";
import { PageHeader } from "@/components/ui-system";
import { createAccountDirectory } from "@/lib/account-directory";
import { dailyReportExportUrl } from "@/lib/api";
import { useOperationsBootstrap } from "@/components/use-operations-bootstrap";

function RouteLoading() {
  return <section className="panel loading-state" aria-live="polite"><span className="skeleton-line short" /><span className="skeleton-line" /><span className="skeleton-line" /><span className="sr-only">Đang tải nội dung trang…</span></section>;
}

const DashboardHome = lazy(() => import("@/components/pages/dashboard").then((module) => ({ default: module.DashboardHome })));
const SavedViews = lazy(() => import("@/components/saved-views").then((module) => ({ default: module.SavedViews })));
const UpdateBanner = lazy(() => import("@/components/update-banner").then((module) => ({ default: module.UpdateBanner })));

export function DashboardOperationsPage() {
  const filters = useUrlFilters();
  const { authError, connectionError, loading, metaData, preferences, retry, updatePreferences, user } = useOperationsBootstrap();
  const accountDirectory = useMemo(
    () => createAccountDirectory(metaData?.account_items, metaData?.accounts),
    [metaData],
  );

  if (loading) return <main className="auth-shell"><section className="auth-card panel"><div className="brand-badge">AFF</div><h1>Đang tải trung tâm vận hành…</h1><p className="hint">Đang kiểm tra phiên đăng nhập và kết nối dữ liệu.</p></section></main>;
  if (authError) return <SignInCard message={authError} />;
  if (connectionError || !user) return <ConnectionErrorCard message={connectionError || "Không thể tải cấu hình ứng dụng."} onRetry={retry} />;
  if (!preferences || !metaData) return <ConnectionErrorCard message="Không thể tải cấu hình ứng dụng." onRetry={retry} />;

  return (
    <AppShell
      user={user}
      appVersion={metaData.app_version ?? ""}
      runtimePlatform={metaData.runtime_platform}
      collapsed={preferences.sidebar_collapsed}
      onCollapsedChange={(collapsed) => updatePreferences({ sidebar_collapsed: collapsed })}
      heading={<PageHeader title="Tổng quan hiệu suất" description="Theo dõi hoa hồng, tiến độ mục tiêu và phạm vi dữ liệu hiện tại." />}
    >
      {metaData.runtime_platform !== "android" ? <Suspense fallback={null}><UpdateBanner capability={metaData.capabilities.update_check} onUpdatePage={false} /></Suspense> : null}
      {metaData.accounts.length ? <>
        <Suspense fallback={null}><SavedViews route="dashboard" /></Suspense>
        <FilterBar
          accounts={metaData.accounts}
          directory={accountDirectory}
          statuses={metaData.statuses}
          actions={<a className="button-link secondary-link" download="affiliate-daily-report.xlsx" href={dailyReportExportUrl({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end })}>Xuất báo cáo ngày</a>}
        />
        <Suspense fallback={<RouteLoading />}><DashboardHome user={user} filters={filters} accounts={metaData.accounts} directory={accountDirectory} preferences={preferences} onPreferencesChange={updatePreferences} /></Suspense>
      </> : <DashboardFirstRun user={user} setup={{ hasAccounts: false, hasImports: false, hasTarget: false }} />}
    </AppShell>
  );
}
