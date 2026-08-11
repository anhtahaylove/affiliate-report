import { expect, test } from "@playwright/test";

test("timeline cập nhật giữ đủ năm bước trên một hàng desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/settings/update/");
  await expect(page.locator(".update-stages li")).toHaveCount(5);

  const rects = await page.locator(".update-stages li").evaluateAll((items) =>
    items.map((item) => {
      const rect = item.getBoundingClientRect();
      return { top: Math.round(rect.top), width: Math.round(rect.width) };
    }),
  );

  expect(new Set(rects.map((rect) => rect.top)).size).toBe(1);
  expect(rects.every((rect) => rect.width >= 120)).toBeTruthy();
  await expect(page.getByRole("button", { name: "Làm mới trạng thái" })).toHaveCount(0);
});

test("timeline cập nhật chuyển thành danh sách một cột rõ ràng trên mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/settings/update/");
  await expect(page.locator(".update-stages li")).toHaveCount(5);

  const rects = await page.locator(".update-stages li").evaluateAll((items) =>
    items.map((item) => {
      const rect = item.getBoundingClientRect();
      return { left: Math.round(rect.left), top: Math.round(rect.top), width: Math.round(rect.width) };
    }),
  );

  expect(new Set(rects.map((rect) => rect.left)).size).toBe(1);
  expect(new Set(rects.map((rect) => rect.top)).size).toBe(5);
  expect(rects.every((rect) => rect.width >= 280)).toBeTruthy();
});
