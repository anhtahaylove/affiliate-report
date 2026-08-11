import { expect, test } from "@playwright/test";

const dashboardLayout = {
  schema: 1,
  order: ["today_pulse", "target_progress", "action_alerts", "trend", "account_contribution", "settlement", "data_freshness", "recent_imports"],
  hidden: [],
};

test("PostgreSQL/OIDC settings explain unavailable local operations without calling them", async ({ page }) => {
  let backupCalls = 0;
  let updateCalls = 0;

  await page.route("**/auth/me", (route) => route.fulfill({
    json: { email: "owner@example.test", role: "owner", accounts: [], auth_method: "oidc", desktop_app: false },
  }));
  await page.route("**/api/v1/meta", (route) => route.fulfill({
    json: {
      accounts: [],
      account_items: [],
      statuses: ["settled", "ineligible", "pending", "unknown"],
      max_upload_mb: 20,
      app_version: "2.0.1",
      capabilities: {
        database_backend: "postgresql",
        auth_mode: "oidc",
        data_admin: { available: false, reason: "PostgreSQL dùng chung được sao lưu và khôi phục ở tầng hạ tầng." },
        update_check: { available: false, reason: "Bản triển khai OIDC dùng chung được cập nhật tại máy chủ." },
        update_install: { available: false, reason: "Bản triển khai OIDC dùng chung được cập nhật tại máy chủ." },
      },
      identity_policy: { mode: "oidc", oidc_allowlist_enforced: true, enforcement: "login_and_active_sessions" },
    },
  }));
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({
    json: { theme: "system", sidebar_collapsed: false, dashboard_layout: dashboardLayout, updated_at: null },
  }));
  await page.route("**/api/v1/admin/backups", (route) => {
    backupCalls += 1;
    return route.fulfill({ status: 500, json: { detail: "must not be called" } });
  });
  await page.route("**/api/v1/admin/update", (route) => {
    updateCalls += 1;
    return route.fulfill({ status: 500, json: { detail: "must not be called" } });
  });
  await page.route("**/api/v1/admin/users", (route) => route.fulfill({
    json: { items: [], count: 0 },
  }));

  await page.goto("/settings/data/");
  await expect(page.getByRole("heading", { name: "Sao lưu và Reset Data được quản lý ngoài ứng dụng" })).toBeVisible();
  await expect(page.getByText("Không gửi lệnh xóa hoặc khôi phục cục bộ")).toBeVisible();
  await expect(page.getByRole("button", { name: "Xóa dữ liệu báo cáo" })).toHaveCount(0);
  expect(backupCalls).toBe(0);

  await page.goto("/settings/update/");
  await expect(page.getByRole("heading", { name: "Phiên bản được cập nhật tại máy chủ" })).toBeVisible();
  await expect(page.getByText("Không tải hoặc chạy installer Windows")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cài bản cập nhật" })).toHaveCount(0);
  expect(updateCalls).toBe(0);

  await page.goto("/settings/users/");
  await expect(page.getByRole("heading", { name: "OIDC allowlist được kiểm tra liên tục" })).toBeVisible();
  await expect(page.getByText("Trạng thái “Đang hoạt động” là điều kiện cần", { exact: false })).toBeVisible();
});
