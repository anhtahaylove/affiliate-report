import { expect, test } from "@playwright/test";

const routes = [
  "/",
  "/analytics/",
  "/orders/",
  "/imports/",
  "/targets/",
  "/accounts/",
  "/settings/preferences/",
  "/settings/data/",
  "/settings/update/",
  "/settings/users/",
] as const;

const viewports = [
  { name: "phone-320", width: 320, height: 720 },
  { name: "phone-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1440", width: 1440, height: 900 },
] as const;

test("mọi route không tràn ngang, không trùng id và giữ đúng cấu trúc responsive", async ({ page }) => {
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);

    for (const route of routes) {
      await page.goto(route);
      await expect(page.locator("h1")).toHaveCount(1);
      await page.waitForLoadState("networkidle");

      const snapshot = await page.evaluate(() => {
        const html = document.documentElement;
        const duplicateIds = [...document.querySelectorAll<HTMLElement>("[id]")]
          .map((element) => element.id)
          .filter((id, index, ids) => id && ids.indexOf(id) !== index);
        const sidebar = document.querySelector<HTMLElement>(".sidebar");
        return {
          overflowX: Math.max(0, html.scrollWidth - html.clientWidth),
          duplicateIds: [...new Set(duplicateIds)],
          sidebarScrollTop: sidebar?.scrollTop ?? 0,
        };
      });

      expect(snapshot.overflowX, `${viewport.name} ${route} không được tràn ngang`).toBeLessThanOrEqual(1);
      expect(snapshot.duplicateIds, `${viewport.name} ${route} không được trùng id`).toEqual([]);
      if (viewport.width > 860) {
        expect(snapshot.sidebarScrollTop, `${viewport.name} ${route} phải bắt đầu sidebar từ đầu`).toBe(0);
      }
    }
  }
});

test("các điều khiển mobile trọng yếu có vùng chạm tối thiểu 44px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/analytics/");

  for (const control of [
    page.getByRole("button", { name: "Mở tìm kiếm nhanh" }),
    page.getByRole("button", { name: "7 ngày" }),
    page.getByRole("tab", { name: "Tài chính" }),
  ]) {
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
  }

  await page.goto("/orders/");
  const columnSummary = page.locator(".column-controls summary");
  const summaryBox = await columnSummary.boundingBox();
  expect(summaryBox).not.toBeNull();
  expect(summaryBox!.height).toBeGreaterThanOrEqual(44);
});
