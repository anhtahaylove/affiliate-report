import AxeBuilder from "@axe-core/playwright";
import { expect, type Locator, type Page, test } from "@playwright/test";

const ROUTES = [
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
];

const SUMMARY_REGIONS = [
  { route: "/accounts/", name: "Tổng quan tài khoản" },
  { route: "/settings/update/", name: "Thông tin phiên bản" },
  { route: "/settings/users/", name: "Tổng quan phân quyền" },
] as const;

const ACCESSIBILITY_VIEWPORTS = [
  { name: "phone-compact", width: 320, height: 720 },
  { name: "phone", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 },
] as const;

function parseRgb(value: string) {
  const channels = value.match(/[\d.]+/g)?.slice(0, 3).map(Number);
  if (!channels || channels.length !== 3) throw new Error(`Không đọc được màu ${value}`);
  return channels;
}

function contrastRatio(foreground: string, background: string) {
  const luminance = (value: string) => {
    const [red, green, blue] = parseRgb(value).map((channel) => {
      const normalized = channel / 255;
      return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  };
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

async function focusWithTab(page: Page, target: Locator) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => document.activeElement === element)) return;
  }
  throw new Error("Không thể đưa focus đến control bằng phím Tab");
}

async function expectFocusIndicator(target: Locator) {
  const focus = await target.evaluate((element) => {
    const style = getComputedStyle(element);
    const parentBackground = getComputedStyle(element.parentElement as Element).backgroundColor;
    const rect = element.getBoundingClientRect();
    return {
      outlineColor: style.outlineColor,
      outlineStyle: style.outlineStyle,
      outlineWidth: Number.parseFloat(style.outlineWidth),
      outlineOffset: Number.parseFloat(style.outlineOffset),
      backgroundColor: style.backgroundColor === "rgba(0, 0, 0, 0)" ? parentBackground : style.backgroundColor,
      rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom },
      viewport: { width: window.innerWidth, height: window.innerHeight },
    };
  });
  const focusExtent = focus.outlineWidth + focus.outlineOffset;
  expect(focus.outlineStyle).toBe("solid");
  expect(focus.outlineWidth).toBeGreaterThanOrEqual(3);
  expect(contrastRatio(focus.outlineColor, focus.backgroundColor)).toBeGreaterThanOrEqual(3);
  expect(focus.rect.left - focusExtent).toBeGreaterThanOrEqual(0);
  expect(focus.rect.top - focusExtent).toBeGreaterThanOrEqual(0);
  expect(focus.rect.right + focusExtent).toBeLessThanOrEqual(focus.viewport.width);
  expect(focus.rect.bottom + focusExtent).toBeLessThanOrEqual(focus.viewport.height);
}

for (const viewport of ACCESSIBILITY_VIEWPORTS) {
  test(`không có axe violation trên ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    for (const route of ROUTES) {
      await page.goto(route);
      await expect(page.locator("main")).toBeVisible();
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(results.violations, `${route} (${viewport.name})`).toEqual([]);
    }
  });
}

test("các vùng tổng quan dùng semantic HTML hợp lệ", async ({ page }) => {
  for (const summary of SUMMARY_REGIONS) {
    await page.goto(summary.route);
    await expect(page.getByRole("region", { name: summary.name })).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    const prohibitedAria = [...results.violations, ...results.incomplete]
      .filter((result) => result.id === "aria-prohibited-attr");
    expect(prohibitedAria, `${summary.route}: aria-prohibited-attr`).toEqual([]);
  }
});

for (const viewport of ACCESSIBILITY_VIEWPORTS) {
  for (const theme of ["light", "dark"] as const) {
    test(`bàn phím và focus ${viewport.name}/${theme} rõ, không bị cắt`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await page.evaluate((value) => document.documentElement.setAttribute("data-theme", value), theme);

      const primaryControl = viewport.width >= 981
        ? page.getByRole("button", { name: /thanh điều hướng/ })
        : page.getByRole("button", { name: "Thêm" });
      await focusWithTab(page, primaryControl);
      await expect(primaryControl).toBeFocused();
      await expectFocusIndicator(primaryControl);
      await page.keyboard.press("Enter");
      if (viewport.width < 981) {
        await expect(page.getByRole("dialog", { name: "Thêm mục" })).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(primaryControl).toBeFocused();
      }

      await page.keyboard.press("Control+KeyK");
      const search = page.getByRole("textbox", { name: "Tìm trang" });
      await expect(search).toBeFocused();
      await expectFocusIndicator(search);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: /Tổng quan/ }).last()).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog", { name: "Đi đến nhanh" })).toHaveCount(0);
    });
  }
}

test("prefers-reduced-motion tắt animation của sheet", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const more = page.getByRole("button", { name: "Thêm" });
  await focusWithTab(page, more);
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog", { name: "Thêm mục" });
  await expect(sheet).toBeVisible();
  const motion = await sheet.evaluate((element) => {
    const style = getComputedStyle(element);
    return { animationName: style.animationName, transitionDuration: style.transitionDuration };
  });
  expect(motion.animationName).toBe("none");
  expect(Number.parseFloat(motion.transitionDuration)).toBeLessThanOrEqual(0.001);
  await page.keyboard.press("Escape");
  await expect(more).toBeFocused();
});
