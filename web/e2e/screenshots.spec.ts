import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

/**
 * Không phải test đúng-sai — đây là công cụ chụp lại giao diện để nhìn bằng mắt sau mỗi lần
 * đổi thiết kế. Gắn thẻ @shots để KHÔNG chạy chung với test thật: cả hai dùng chung một
 * database tạm, chạy song song thì mỗi bên thấy dữ liệu của bên kia. Chạy bằng: pnpm shots
 */
const SAMPLE = resolve(__dirname, "..", "..", "tests", "fixtures", "affiliate_orders_e2e-sample.xlsx");
const ACCOUNT = "SHOTSHOP";
const SCOPE = `?start=2026-03-01&end=2026-03-31&account=${ACCOUNT}`;

test("@shots chụp các màn hình chính ở cả hai chế độ màu", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/accounts/");
  await page.getByLabel("Mã tài khoản").fill(ACCOUNT);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await expect(page.getByText(`Đã tạo tài khoản ${ACCOUNT}.`)).toBeVisible();

  await page.goto("/imports/");
  await page.getByLabel("Tài khoản TikTok").selectOption(ACCOUNT);
  await page.getByLabel("File Excel đã xuất từ TikTok").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Nhập dữ liệu" }).click();
  await expect(page.locator(".import-result")).toHaveCount(1);

  for (const theme of ["dark", "light"] as const) {
    // Database là source of truth; localStorage chỉ dùng để tránh loé màu trước lần tải đầu.
    const saved = await page.request.patch("/api/v1/ui/preferences", { data: { theme } });
    expect(saved.ok()).toBeTruthy();

    await page.goto(`/${SCOPE}`);
    await expect(page.locator("article.pulse-metric").first()).toBeVisible();
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible();
    await page.screenshot({ path: `e2e/shots/dashboard-${theme}.png`, fullPage: true });

    await page.goto(`/orders/${SCOPE}`);
    await expect(page.getByRole("heading", { level: 2 })).toContainText("đơn trong bộ lọc");
    await page.screenshot({ path: `e2e/shots/orders-${theme}.png`, fullPage: true });

    await page.goto(`/targets/${SCOPE}`);
    // Chờ số liệu chứ không chờ tiêu đề: tiêu đề là chữ tĩnh nên hiện ngay, ảnh sẽ chụp
    // đúng lúc mọi con số còn là dấu gạch.
    await expect(page.locator(".target-card").first()).toContainText("₫");
    await page.screenshot({ path: `e2e/shots/targets-${theme}.png`, fullPage: true });
  }

  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto(`/${SCOPE}`);
  await expect(page.locator(".recharts-wrapper").first()).toBeVisible();
  await page.screenshot({ path: "e2e/shots/dashboard-tablet-768.png", fullPage: true });

  await page.goto(`/orders/${SCOPE}`);
  await expect(page.getByRole("heading", { level: 2 })).toContainText("đơn trong bộ lọc");
  await page.screenshot({ path: "e2e/shots/orders-tablet-768.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/${SCOPE}`);
  await expect(page.locator("article.pulse-metric").first()).toBeVisible();
  // Ở 390px các khối phân tích phụ nằm trong disclosure thu gọn (v2.0.4), nên biểu đồ chưa được
  // dựng. Đòi .recharts-wrapper ở đây là đòi thứ mà chính thiết kế mobile cố tình giấu đi — ảnh
  // phải chụp đúng trạng thái mặc định người dùng thấy, không phải trạng thái đã mở sẵn.
  await page.screenshot({ path: "e2e/shots/dashboard-mobile-390.png", fullPage: true });

  await page.goto(`/orders/${SCOPE}`);
  await expect(page.locator(".order-card").first()).toBeVisible();
  await page.screenshot({ path: "e2e/shots/orders-mobile-390.png", fullPage: true });

  const auditRoutes = [
    ["analytics", `/analytics/${SCOPE}`, ".recharts-wrapper"],
    ["imports", "/imports/", ".imports-workflow-page"],
    ["targets", `/targets/${SCOPE}`, ".target-card"],
    ["accounts", "/accounts/", ".account-card"],
    ["preferences", "/settings/preferences/", ".theme-preference-grid"],
    ["data", "/settings/data/", ".settings-overview"],
    ["update", "/settings/update/", ".update-settings-page"],
    ["users", "/settings/users/", ".settings-summary-row"],
  ] as const;

  for (const viewport of [
    { name: "desktop", width: 1440, height: 900 },
    { name: "mobile", width: 390, height: 844 },
  ] as const) {
    await page.setViewportSize(viewport);
    for (const [name, route, readySelector] of auditRoutes) {
      await page.goto(route);
      await expect(page.locator(readySelector).first()).toBeVisible();
      await page.screenshot({ path: `e2e/shots/audit-${name}-${viewport.name}.png`, fullPage: true });
    }
  }
});
