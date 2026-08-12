import { expect, test, type Page } from "@playwright/test";

const dashboardLayout = {
  schema: 1,
  order: ["today_pulse", "target_progress", "action_alerts", "trend", "account_contribution", "settlement", "data_freshness", "recent_imports"],
  hidden: [],
};

type ShellOptions = {
  role?: "owner" | "operator" | "viewer";
  accounts?: Array<{ code: string; display_name: string; active: boolean; display_order: number }>;
};

async function mockShell(page: Page, options: ShellOptions = {}) {
  const role = options.role ?? "owner";
  const accountItems = options.accounts ?? [];
  await page.route("**/auth/me", (route) => route.fulfill({ json: { email: `${role}@example.test`, role, accounts: accountItems.map((item) => item.code), auth_method: "local", desktop_app: false } }));
  await page.route("**/api/v1/meta", (route) => route.fulfill({
    json: {
      accounts: accountItems.map((item) => item.code),
      account_items: accountItems,
      statuses: ["settled", "pending", "ineligible", "unknown"],
      max_upload_mb: 50,
      app_version: "2.0.4",
      capabilities: {
        database_backend: "sqlite",
        auth_mode: "local",
        data_admin: { available: true, reason: null },
        update_check: { available: true, reason: null },
        update_install: { available: true, reason: null },
      },
      identity_policy: { mode: "local", oidc_allowlist_enforced: false, enforcement: "local_owner" },
    },
  }));
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({ json: { theme: "system", sidebar_collapsed: false, dashboard_layout: dashboardLayout, updated_at: null } }));
  await page.route("**/api/v1/ui/saved-views**", (route) => route.fulfill({ json: { items: [], count: 0 } }));
}

function emptyAnalytics() {
  return {
    filters: { accounts: [], start: null, end: null, statuses: [], group_by: "day", top: 10 },
    summary: { orders: 0, order_lines: 0, gross_gmv: 0, actual_gmv: 0, initial_commission: 0, actual_commission: 0, final_received: 0, units_sold: 0, units_refunded: 0, effective_commission_rate: null, refund_rate: null, ineligible_rate: null, final_received_variance: 0, latest_order_date: null },
    previous_period: null,
    target: null,
    trend: [], status_breakdown: [], account_breakdown: [], products: [], shops: [], content: [],
    settlement: { median_lag_days: null, settled_lines: 0, pending_lines: 0, pending_aging: [] },
    data_quality: { unknown_status_rows: 0, non_vnd_rows: 0, missing_order_date_rows: 0, missing_settlement_date_rows: 0, settled_missing_settlement_rows: 0, negative_settlement_lag_rows: 0, import_batches: 0, import_inserted: 0, import_updated: 0, import_unchanged: 0, import_rejected: 0, latest_import_at: null },
  };
}

async function mockEmptyDashboard(page: Page, onTargetMonth?: (month: string | null) => void) {
  await page.route("**/api/v1/overview**", (route) => route.fulfill({ json: { items: [], count: 0 } }));
  await page.route("**/api/v1/daily**", (route) => route.fulfill({ json: { items: [], count: 0 } }));
  await page.route("**/api/v1/monthly-kpi**", (route) => route.fulfill({ json: { items: [], count: 0 } }));
  await page.route("**/api/v1/analytics**", (route) => route.fulfill({ json: emptyAnalytics() }));
  await page.route("**/api/v1/targets**", (route) => {
    onTargetMonth?.(new URL(route.request().url()).searchParams.get("month"));
    return route.fulfill({ json: { items: [], count: 0 } });
  });
  await page.route("**/api/v1/imports**", (route) => route.fulfill({ json: { items: [], count: 0, limit: 20 } }));
}

test("owner and operator receive role-aware first-run guidance", async ({ page }) => {
  let onboardingTargetMonth: string | null = null;
  await mockShell(page);
  await mockEmptyDashboard(page, (month) => { onboardingTargetMonth = month; });
  await page.goto("/?month=2025-01&start=2025-01-01&end=2025-01-31");
  await expect(page.getByRole("heading", { name: "Hoàn tất thiết lập vận hành" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Tạo account TikTok" })).toBeVisible();
  const now = new Date();
  await expect.poll(() => onboardingTargetMonth).toBe(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);

  await page.unrouteAll({ behavior: "wait" });
  await mockShell(page, { role: "operator" });
  await mockEmptyDashboard(page);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Liên hệ chủ sở hữu để được cấp account" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Tạo account TikTok" })).toHaveCount(0);
});

test("imports zero-account state is safe and successful import keeps results plus next actions", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/imports**", (route) => route.fulfill({ json: { items: [], count: 0, limit: 20 } }));
  await page.goto("/imports/");
  await expect(page.getByRole("heading", { name: "Tạo account trước khi nhập dữ liệu" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Tạo account đầu tiên" })).toBeVisible();
  await expect(page.getByLabel("1. Tài khoản TikTok")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Nhập dữ liệu" })).toHaveCount(0);

  await page.unrouteAll({ behavior: "wait" });
  const account = { code: "SHOP_A", display_name: "Gian hàng chính", active: true, display_order: 1 };
  await mockShell(page, { accounts: [account] });
  let historyItems: unknown[] = [];
  await page.route("**/api/v1/imports**", async (route) => {
    if (route.request().method() === "POST") {
      historyItems = [{ id: 1, filename: "orders.xlsx", account: "SHOP_A", inserted: 2, updated: 0, unchanged: 0, rejected: 0, created_at: "2026-08-12T00:00:00Z" }];
      return route.fulfill({ json: { inserted: 2, updated: 0, unchanged: 0, rejected: 0, duplicate: false, rejected_rows: [] } });
    }
    return route.fulfill({ json: { items: historyItems, count: historyItems.length, limit: 20 } });
  });
  await page.reload();
  await expect(page.getByLabel("1. Tài khoản TikTok")).toHaveValue("SHOP_A");
  await expect(page.getByLabel("1. Tài khoản TikTok").locator("option")).toHaveText("Gian hàng chính — SHOP_A");
  await page.getByLabel("File Excel đã xuất từ TikTok").setInputFiles({ name: "orders.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("fixture") });
  await page.getByRole("button", { name: "Nhập dữ liệu" }).click();
  await expect(page.getByText("2 dòng mới", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "Xem Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Đặt mục tiêu tháng" })).toBeVisible();
});

test("rename keeps committed result when shell metadata refresh fails and retry recovers", async ({ page }) => {
  let currentName = "Gian hàng cũ";
  let metaCalls = 0;
  let failNextRefresh = false;
  const record = () => ({ code: "SHOP_A", display_name: currentName, active: true, display_order: 1, created_at: null, updated_at: null });
  await page.route("**/auth/me", (route) => route.fulfill({ json: { email: "owner@example.test", role: "owner", accounts: ["SHOP_A"], auth_method: "local", desktop_app: false } }));
  await page.route("**/api/v1/meta", (route) => {
    metaCalls += 1;
    if (failNextRefresh) {
      failNextRefresh = false;
      return route.fulfill({ status: 503, json: { detail: "metadata temporarily unavailable" } });
    }
    return route.fulfill({ json: { accounts: ["SHOP_A"], account_items: [record()], statuses: [], max_upload_mb: 50, app_version: "2.0.4", capabilities: { database_backend: "sqlite", auth_mode: "local", data_admin: { available: true, reason: null }, update_check: { available: true, reason: null }, update_install: { available: true, reason: null } }, identity_policy: { mode: "local", oidc_allowlist_enforced: false, enforcement: "local_owner" } } });
  });
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({ json: { theme: "system", sidebar_collapsed: false, dashboard_layout: dashboardLayout, updated_at: null } }));
  await page.route("**/api/v1/accounts**", async (route) => {
    if (route.request().method() === "PATCH") {
      currentName = ((await route.request().postDataJSON()) as { display_name: string }).display_name;
      failNextRefresh = true;
      return route.fulfill({ json: record() });
    }
    return route.fulfill({ json: { items: [record()], count: 1, hard_delete_supported: true } });
  });

  await page.goto("/accounts/");
  await page.getByLabel("Tên hiển thị", { exact: true }).fill("Gian hàng mới");
  await page.getByRole("button", { name: "Lưu thay đổi" }).click();
  await expect(page.getByLabel("Tên hiển thị", { exact: true })).toHaveValue("Gian hàng mới");
  await expect(page.locator(".sync-warning")).toContainText("Thay đổi đã được lưu");
  await expect(page).toHaveURL(/\/accounts\/$/);
  await page.getByRole("button", { name: "Thử đồng bộ lại" }).click();
  await expect(page.getByText("Đã đồng bộ tên tài khoản trên toàn ứng dụng.")).toBeVisible();
  expect(metaCalls).toBe(3);
});

test("account mutations refresh metadata once only after a successful commit", async ({ page }) => {
  type AccountRecord = { code: string; display_name: string; active: boolean; display_order: number; created_at: null; updated_at: null };
  let records: AccountRecord[] = [
    { code: "BASE", display_name: "Tài khoản nền", active: true, display_order: 1, created_at: null, updated_at: null },
  ];
  let metaCalls = 0;
  let failNextDelete = true;

  await page.route("**/auth/me", (route) => route.fulfill({ json: { email: "owner@example.test", role: "owner", accounts: records.map((item) => item.code), auth_method: "local", desktop_app: false } }));
  await page.route("**/api/v1/meta", (route) => {
    metaCalls += 1;
    return route.fulfill({ json: { accounts: records.filter((item) => item.active).map((item) => item.code), account_items: records, statuses: [], max_upload_mb: 50, app_version: "2.0.4", capabilities: { database_backend: "sqlite", auth_mode: "local", data_admin: { available: true, reason: null }, update_check: { available: true, reason: null }, update_install: { available: true, reason: null } }, identity_policy: { mode: "local", oidc_allowlist_enforced: false, enforcement: "local_owner" } } });
  });
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({ json: { theme: "system", sidebar_collapsed: false, dashboard_layout: dashboardLayout, updated_at: null } }));
  await page.route("**/api/v1/accounts**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname;
    if (method === "GET" && path.endsWith("/delete-preview")) {
      const code = decodeURIComponent(path.split("/").at(-2) ?? "");
      return route.fulfill({ json: { code, exists: true, dependency_counts: {}, can_hard_delete: true, postgres_action: "archive", action: "hard_delete" } });
    }
    if (method === "GET") return route.fulfill({ json: { items: records, count: records.length, hard_delete_supported: true } });
    if (method === "POST") {
      const body = request.postDataJSON() as { code: string; display_name: string };
      if (body.code === "FAIL") return route.fulfill({ status: 422, json: { detail: "Không thể tạo" } });
      const created: AccountRecord = { code: body.code, display_name: body.display_name, active: true, display_order: records.length + 1, created_at: null, updated_at: null };
      records = [...records, created];
      return route.fulfill({ json: created });
    }
    const code = decodeURIComponent(path.split("/").at(-1) ?? "");
    if (method === "PATCH") {
      const body = request.postDataJSON() as { display_name?: string; display_order?: number; active?: boolean };
      if (body.display_name === "Không lưu") return route.fulfill({ status: 422, json: { detail: "Không thể cập nhật" } });
      const current = records.find((item) => item.code === code)!;
      const updated = { ...current, ...Object.fromEntries(Object.entries(body).filter(([, value]) => value !== undefined)) };
      records = records.map((item) => item.code === code ? updated : item);
      return route.fulfill({ json: updated });
    }
    if (method === "DELETE") {
      if (failNextDelete) {
        failNextDelete = false;
        return route.fulfill({ status: 500, json: { detail: "Không thể xóa" } });
      }
      records = records.filter((item) => item.code !== code);
      return route.fulfill({ json: { code, archived: false, hard_deleted: true, backup_path: "backup.db", dependency_counts: {} } });
    }
    return route.abort();
  });

  await page.goto("/accounts/");
  await expect(page.getByRole("heading", { name: "Quản lý tài khoản đang dùng và đã lưu trữ" })).toBeVisible();
  await expect.poll(() => metaCalls).toBe(1);

  await page.getByLabel("Mã tài khoản mới").fill("NEW_ACC");
  await page.getByLabel("Tên hiển thị mới (không bắt buộc)").fill("Cửa hàng mới");
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await expect(page.locator(".account-card").filter({ hasText: "NEW_ACC" })).toBeVisible();
  await expect.poll(() => metaCalls).toBe(2);

  await page.getByLabel("Mã tài khoản mới").fill("FAIL");
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await expect(page.getByText("Không thể tạo", { exact: false })).toBeVisible();
  expect(metaCalls).toBe(2);

  let card = page.locator(".account-card").filter({ hasText: "NEW_ACC" });
  await card.getByRole("button", { name: "Lưu trữ" }).click();
  await expect(card.getByRole("button", { name: "Kích hoạt lại" })).toBeVisible();
  await expect.poll(() => metaCalls).toBe(3);

  await card.getByLabel("Tên hiển thị").fill("Không lưu");
  await card.getByRole("button", { name: "Lưu thay đổi" }).click();
  await expect(page.getByText("Không thể cập nhật", { exact: false })).toBeVisible();
  expect(metaCalls).toBe(3);

  await card.getByRole("button", { name: "Kích hoạt lại" }).click();
  card = page.locator(".account-card").filter({ hasText: "NEW_ACC" });
  await expect(card.getByRole("button", { name: "Lưu trữ" })).toBeVisible();
  await expect.poll(() => metaCalls).toBe(4);

  await card.getByRole("button", { name: "Xem trước khi xóa" }).click();
  await page.getByLabel("Nhập chính xác XOA NEW_ACC").fill("XOA NEW_ACC");
  await page.getByRole("button", { name: "Xóa vĩnh viễn" }).click();
  await expect(page.getByText("Không thể xóa", { exact: false })).toBeVisible();
  expect(metaCalls).toBe(4);

  await page.getByRole("button", { name: "Xóa vĩnh viễn" }).click();
  await expect(page.locator(".account-card").filter({ hasText: "NEW_ACC" })).toHaveCount(0);
  await expect.poll(() => metaCalls).toBe(5);
});
