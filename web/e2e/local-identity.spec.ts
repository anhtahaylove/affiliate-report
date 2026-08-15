import { expect, test } from "@playwright/test";

const dashboardLayout = {
  schema: 1,
  order: ["today_pulse", "target_progress", "action_alerts", "trend", "account_contribution", "settlement", "data_freshness", "recent_imports"],
  hidden: [],
};

// Bản cài trên máy chỉ có đúng một danh tính: auth.py trả local_principal() bất kể session
// token, nên "Đăng xuất" thu hồi một session mà xác thực không hề tra tới — bấm xong chỉ
// tải lại trang rồi quay về đúng chỗ cũ. Trang Người dùng và chip vai trò cũng không còn
// nghĩa khi chỉ có một người. Ẩn chúng ở chế độ cục bộ, giữ nguyên cho bản dùng chung.
test("bản cài cục bộ không bày Đăng xuất, Người dùng hay chip vai trò", async ({ page }) => {
  let logoutCalls = 0;
  await page.route("**/auth/logout", (route) => {
    logoutCalls += 1;
    return route.fulfill({ status: 500, json: { detail: "must not be called" } });
  });

  await page.goto("/");
  await expect(page.locator(".sidebar-brand")).toBeVisible();

  await expect(page.getByRole("button", { name: "Đăng xuất" })).toHaveCount(0);
  await expect(page.locator(".user-menu")).toHaveCount(0);
  await expect(page.locator('.sidebar a[href="/settings/users/"]')).toHaveCount(0);

  // Kể cả trong bottom sheet "Thêm" của mobile.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Thêm" }).click();
  await expect(page.getByRole("dialog", { name: "Thêm mục" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Đăng xuất" })).toHaveCount(0);
  await expect(page.getByRole("dialog").locator('a[href="/settings/users/"]')).toHaveCount(0);

  expect(logoutCalls, "không được gọi /auth/logout ở chế độ cục bộ").toBe(0);
});

test("bản triển khai dùng chung vẫn giữ đủ Đăng xuất, Người dùng và danh tính", async ({ page }) => {
  await page.route("**/auth/me", (route) => route.fulfill({
    json: { email: "owner@example.test", display_name: "Owner", role: "owner", accounts: [], auth_method: "oidc", desktop_app: false },
  }));
  await page.route("**/api/v1/meta", (route) => route.fulfill({
    json: {
      accounts: [],
      account_items: [],
      statuses: ["settled", "ineligible", "pending", "unknown"],
      max_upload_mb: 20,
      app_version: "2.1.2",
      runtime_platform: "web",
      capabilities: {
        database_backend: "postgresql",
        auth_mode: "oidc",
        data_admin: { available: false, reason: "PostgreSQL dùng chung." },
        update_check: { available: false, reason: "Cập nhật tại máy chủ." },
        update_install: { available: false, reason: "Cập nhật tại máy chủ." },
      },
      identity_policy: { mode: "oidc", oidc_allowlist_enforced: true, enforcement: "login_and_active_sessions" },
    },
  }));
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({
    json: { theme: "system", sidebar_collapsed: false, dashboard_layout: dashboardLayout, updated_at: null },
  }));

  await page.goto("/");
  await expect(page.locator(".sidebar-brand")).toBeVisible();

  await expect(page.getByRole("button", { name: "Đăng xuất" })).toBeVisible();
  await expect(page.locator(".user-menu")).toContainText("owner@example.test");
  await expect(page.locator('.sidebar a[href="/settings/users/"]')).toHaveCount(1);
});
