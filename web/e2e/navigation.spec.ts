import { expect, test } from "@playwright/test";

const ROUTES = [
  ["/", "/"],
  ["/analytics/", "/analytics/"],
  ["/orders/", "/orders/"],
  ["/imports/", "/imports/"],
  ["/targets/", "/targets/"],
  ["/accounts/", "/accounts/"],
  ["/settings/preferences/", "/settings/preferences/"],
  ["/settings/data/", "/settings/data/"],
  ["/settings/update/", "/settings/update/"],
  ["/settings/users/", "/settings/users/"],
] as const;

test("sidebar giữ đúng route, highlight mọi page và mở rộng không điều hướng về Tổng quan", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.request.patch("/api/v1/ui/preferences", { data: { sidebar_collapsed: false } });

  for (const [route, href] of ROUTES) {
    await page.goto(route);
    const current = page.locator('.sidebar nav a[aria-current="page"]');
    await expect(current).toHaveCount(1);
    await expect(current).toHaveAttribute("href", href);
  }

  await page.goto("/analytics/");
  await page.getByRole("button", { name: "Thu gọn thanh điều hướng" }).click();
  await expect(page.locator(".cockpit-shell")).toHaveClass(/sidebar-collapsed/);
  await expect(page.getByRole("link", { name: "Phân tích" })).toBeVisible();
  await page.getByRole("button", { name: "Mở rộng thanh điều hướng" }).click();
  await expect(page).toHaveURL(/\/analytics\/$/);
  await expect(page.locator(".cockpit-shell")).not.toHaveClass(/sidebar-collapsed/);
  await expect(page.locator('.sidebar nav a[aria-current="page"]')).toHaveAttribute("href", "/analytics/");
  await expect(page.getByText("Momentum Canvas", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Momentum", { exact: true })).toHaveCount(0);

  await page.goto("/settings/update/");
  await expect(page.locator('.settings-tabs a[aria-current="page"]')).toHaveAttribute("href", "/settings/update/");
});

test("mobile đánh dấu mục Thêm khi route hiện tại nằm trong action sheet", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/analytics/");

  await expect(page.getByRole("button", { name: "Thêm" })).toHaveAttribute("aria-current", "page");
});
