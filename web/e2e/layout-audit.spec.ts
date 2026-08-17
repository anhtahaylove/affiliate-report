import { expect, test } from "@playwright/test";
import { findClippedElements } from "./clipping";

const routes = [
  "/",
  "/analytics/",
  "/orders/",
  "/imports/",
  "/targets/",
  "/accounts/",
  "/settings/preferences/",
  "/settings/data/",
  "/settings/sync/",
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
  await page.route("**/api/v1/admin/update", (route) => route.fulfill({
    json: {
      current_version: "2.2.0",
      latest_version: "2.2.0",
      available: false,
      installable: false,
      release_url: null,
      message: "Bạn đang dùng bản mới nhất.",
    },
  }));

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
      const clipped = await findClippedElements(page);

      expect(snapshot.overflowX, `${viewport.name} ${route} không được tràn ngang`).toBeLessThanOrEqual(1);
      expect(snapshot.duplicateIds, `${viewport.name} ${route} không được trùng id`).toEqual([]);
      expect(clipped, `${viewport.name} ${route} có phần tử bị overflow:hidden cắt mất nội dung`).toEqual([]);
      if (viewport.width > 860) {
        expect(snapshot.sidebarScrollTop, `${viewport.name} ${route} phải bắt đầu sidebar từ đầu`).toBe(0);
      }
    }
  }
});

test("các điều khiển mobile trọng yếu có vùng chạm tối thiểu 44px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/analytics/");

  const mobileNav = page.locator(".mobile-bottom-nav");
  await expect(mobileNav.locator(":scope > *")).toHaveCount(4);
  expect(await mobileNav.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length)).toBe(4);

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

  await page.goto("/settings/sync/");
  for (const control of [
    page.getByRole("button", { name: "Tạo mật khẩu" }),
    page.locator(".sync-file-picker .file-picker-button"),
  ]) {
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
  }
});

test("hộp xác nhận hiện giữa màn hình chứ không dồn về góc", async ({ page }) => {
  // Lỗi thật ở v2.0.22: hộp xác nhận cài bản cập nhật nằm ở góc trái trên, đo được (0, 0).
  // Trình duyệt căn giữa dialog modal bằng inset:0 + margin:auto mặc định, nhưng giá trị đó
  // bị mất nên phải nói thẳng trong CSS. Bỏ hai dòng đó ra thì test này đỏ.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/settings/update/");

  const hop = page.locator("dialog.confirm-dialog").first();
  await expect(hop).toHaveCount(1);
  const o = await hop.evaluate((el: HTMLDialogElement) => {
    if (!el.open) el.showModal();
    const r = el.getBoundingClientRect();
    return { top: r.top, left: r.left, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight };
  });

  expect(Math.abs((o.vw - o.w) / 2 - o.left)).toBeLessThan(2);
  expect(Math.abs((o.vh - o.h) / 2 - o.top)).toBeLessThan(2);
});
