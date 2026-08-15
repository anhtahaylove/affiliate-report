import { expect, test } from "@playwright/test";

const dashboardLayout = {
  schema: 1,
  order: ["today_pulse", "target_progress", "action_alerts", "trend", "account_contribution", "settlement", "data_freshness", "recent_imports"],
  hidden: [],
};

// Trước đây mất kết nối (app bị Thoát, mạng đứt, backend lỗi) và phiên OIDC hết hạn dùng
// CHUNG một thẻ với nút "Đăng nhập" — vô dụng khi backend đã chết hẳn, vì bấm vào cũng gọi
// lại đúng chỗ không phản hồi. Ở bản cài một danh tính, principal_from_session() luôn trả
// local_principal() bất kể session nên 401 KHÔNG BAO GIỜ tự nhiên xảy ra ở đó; hai bài dưới
// đây kiểm cả hai chiều để không ai vô tình gộp lại thẻ chung.

test("mất kết nối hiện nút Thử lại, không hiện Đăng nhập", async ({ page }) => {
  await page.route("**/auth/me", (route) => route.abort("connectionrefused"));
  await page.route("**/api/v1/meta", (route) => route.abort("connectionrefused"));
  await page.route("**/api/v1/ui/preferences", (route) => route.abort("connectionrefused"));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Không kết nối được tới ứng dụng" })).toBeVisible();
  await expect(page.getByText("Nếu bạn vừa chọn Thoát ứng dụng", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "Đăng nhập" })).toHaveCount(0);

  const retry = page.getByRole("button", { name: "Thử lại" });
  await expect(retry).toBeVisible();
  await expect(retry.locator("svg")).toHaveCount(1);

  // Bấm Thử lại phải gọi lại đúng luồng tải (load()), không phải window.location.reload():
  // đếm số lần /api/v1/meta bị gọi để chứng minh nó re-fetch qua React state, không nạp lại
  // toàn trang. Lần hai trả dữ liệu thật, chứng minh app thoát khỏi ConnectionErrorCard.
  let metaCalls = 0;
  await page.unroute("**/api/v1/meta");
  await page.route("**/api/v1/meta", (route) => {
    metaCalls += 1;
    return route.fulfill({
      json: {
        accounts: [], account_items: [], statuses: ["settled", "ineligible", "pending", "unknown"],
        max_upload_mb: 20, app_version: "2.1.3", runtime_platform: "windows",
        capabilities: {
          database_backend: "sqlite", auth_mode: "local",
          data_admin: { available: true, reason: null }, sync: { available: true, reason: null },
          update_check: { available: true, reason: null }, update_install: { available: true, reason: null },
          android_update: { available: false, reason: "Android only" },
        },
        identity_policy: { mode: "local", oidc_allowlist_enforced: false, enforcement: "local_owner" },
      },
    });
  });
  await page.unroute("**/auth/me");
  await page.route("**/auth/me", (route) => route.fulfill({
    json: { email: "local-owner@localhost", display_name: "Local owner", role: "owner", accounts: [], auth_method: "local", desktop_app: false },
  }));
  await page.unroute("**/api/v1/ui/preferences");
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({
    json: { theme: "system", sidebar_collapsed: false, dashboard_layout: dashboardLayout, updated_at: null },
  }));

  await retry.click();
  await expect(page.locator(".sidebar-brand")).toBeVisible();
  expect(metaCalls).toBeGreaterThan(0);
});

test("phiên OIDC hết hạn (401 thật) hiện nút Đăng nhập, không hiện Thử lại", async ({ page }) => {
  await page.route("**/auth/me", (route) => route.fulfill({ status: 401, json: { detail: "Authentication required" } }));
  await page.route("**/api/v1/meta", (route) => route.fulfill({ status: 401, json: { detail: "Authentication required" } }));
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({ status: 401, json: { detail: "Authentication required" } }));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Affiliate Report" })).toBeVisible();
  const login = page.getByRole("link", { name: "Đăng nhập" });
  await expect(login).toBeVisible();
  await expect(login).toHaveAttribute("href", /\/auth\/login$/);
  await expect(page.getByRole("button", { name: "Thử lại" })).toHaveCount(0);
});
