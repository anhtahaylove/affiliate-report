import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const SAMPLE = resolve(__dirname, "..", "..", "tests", "fixtures", "affiliate_orders_e2e-sample.xlsx");
const ACCOUNT = "MOBILESHOP";
const SCOPE = `?start=2026-03-01&end=2026-03-31&account=${ACCOUNT}`;

test("dashboard mobile ưu tiên nhịp hôm nay và thu gọn phân tích thứ cấp", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto("/accounts/");
  await page.getByLabel("Mã tài khoản").fill(ACCOUNT);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await expect(page.getByText(`Đã tạo tài khoản ${ACCOUNT}.`)).toBeVisible();

  await page.goto("/imports/");
  await page.getByLabel("Tài khoản TikTok").selectOption(ACCOUNT);
  await page.getByLabel("File Excel đã xuất từ TikTok").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Nhập dữ liệu" }).click();
  await expect(page.locator(".import-result")).toHaveAttribute("data-outcome", "imported");

  await page.goto(`/${SCOPE}`);
  await expect(page.locator("[data-widget-id='today_pulse']")).toBeVisible();
  await expect(page.locator("[data-widget-id='target_progress']")).toBeVisible();
  await expect(page.locator("[data-widget-id='action_alerts']")).toBeVisible();

  const disclosures = page.getByTestId("dashboard-disclosure");
  await expect(disclosures).toHaveCount(6);
  await expect(disclosures.first()).not.toHaveAttribute("open", "");

  const trend = page.locator("details[data-widget-id='trend']");
  const trendSummary = trend.locator("summary");
  const targetBox = await page.locator("[data-widget-id='target_progress']").boundingBox();
  const actionBox = await page.locator("[data-widget-id='action_alerts']").boundingBox();
  const trendBox = await trend.boundingBox();
  const summaryBox = await trendSummary.boundingBox();

  expect(targetBox).not.toBeNull();
  expect(actionBox).not.toBeNull();
  expect(trendBox).not.toBeNull();
  expect(summaryBox).not.toBeNull();
  expect(actionBox!.y).toBeGreaterThan(targetBox!.y);
  expect(trendBox!.y).toBeGreaterThan(actionBox!.y);
  expect(summaryBox!.height).toBeGreaterThanOrEqual(44);

  await trendSummary.focus();
  await page.keyboard.press("Enter");
  await expect(trend).toHaveAttribute("open", "");
  await expect(trend.getByRole("heading", { name: "Hoa hồng và tiền đã nhận" })).toBeVisible();
  await page.keyboard.press("Space");
  await expect(trend).not.toHaveAttribute("open", "");

  const widgetIds = await page.locator("[data-widget-id]").evaluateAll((nodes) =>
    nodes.map((node) => node.getAttribute("data-widget-id")),
  );
  expect(widgetIds).toEqual(expect.arrayContaining([
    "today_pulse",
    "target_progress",
    "action_alerts",
    "trend",
    "account_contribution",
    "settlement",
    "data_freshness",
    "recent_imports",
  ]));

  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto(`/${SCOPE}`);
  const compactSummary = page.locator("details[data-widget-id='trend'] summary");
  const compactSummaryBox = await compactSummary.boundingBox();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(compactSummaryBox).not.toBeNull();
  expect(compactSummaryBox!.height).toBeGreaterThanOrEqual(44);
  expect(overflow).toBeLessThanOrEqual(1);

  const customizer = page.getByTestId("dashboard-customizer");
  await customizer.locator("summary").click();
  const trendControls = customizer.locator('[data-widget-control="trend"]');
  await trendControls.getByRole("button", { name: "Ẩn", exact: true }).click();
  await expect(page.locator("details[data-widget-id='trend']")).toBeHidden();
  await trendControls.getByRole("button", { name: "Hiện", exact: true }).click();
  await expect(page.locator("details[data-widget-id='trend']")).toBeVisible();

  const axe = await new AxeBuilder({ page })
    .include('[data-testid="commerce-dashboard"]')
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const blocking = axe.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious");
  expect(blocking).toEqual([]);
});

test("dashboard desktop tiếp tục hiển thị đầy đủ nội dung thứ cấp", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/${SCOPE}`);

  const disclosures = page.getByTestId("dashboard-disclosure");
  await expect(disclosures).toHaveCount(6);
  await expect(disclosures.first()).toHaveAttribute("open", "");
  await expect(disclosures.first().locator("summary")).toBeHidden();
  await expect(page.getByRole("heading", { name: "Hoa hồng và tiền đã nhận" })).toBeVisible();
});
