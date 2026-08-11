import { expect, test } from "@playwright/test";

for (const viewport of [
  { width: 320, height: 720 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
] as const) {
  test(`Momentum mobile ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByRole("navigation", { name: "Điều hướng nhanh mobile" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Điều hướng nhanh mobile" }).getByRole("link")).toHaveCount(3);
    await page.getByRole("button", { name: "Thêm" }).click();
    await expect(page.getByRole("dialog", { name: "Thêm mục" })).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /Phạm vi báo cáo/ }).click();
    await expect(page.getByText("Bộ lọc báo cáo", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Đóng bộ lọc" }).last().click();
  });
}

test("theme chỉ xuất hiện trong Cài đặt", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("radiogroup", { name: "Chọn chế độ giao diện" })).toHaveCount(0);
  await page.goto("/settings/preferences/");
  await expect(page.getByRole("radiogroup", { name: "Chọn chế độ giao diện" })).toBeVisible();
});
