import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

/**
 * Không phải test đúng-sai — đây là công cụ chụp lại giao diện để nhìn bằng mắt sau mỗi lần
 * đổi thiết kế. Gắn thẻ @shots để KHÔNG chạy chung với test thật: cả hai dùng chung một
 * database tạm, chạy song song thì mỗi bên thấy dữ liệu của bên kia. Chạy bằng: pnpm shots
 */
const SAMPLE = resolve(__dirname, "..", "..", "tests", "fixtures", "e2e-sample.xlsx");
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
    // Đặt vào localStorage chứ không gán thẳng data-theme: mỗi lần chuyển trang là DOM dựng
    // lại từ đầu, nên ảnh của các trang sau lần chụp đầu đều bị chụp ở màu hệ thống.
    await page.evaluate((value) => window.localStorage.setItem("tiktok-affiliate-theme", value), theme);

    await page.goto(`/${SCOPE}`);
    await expect(page.locator("article.metric").first()).toBeVisible();
    await page.screenshot({ path: `e2e/shots/dashboard-${theme}.png`, fullPage: true });

    await page.goto(`/orders/${SCOPE}`);
    await expect(page.getByRole("heading", { level: 2 })).toContainText("đơn trong bộ lọc");
    await page.screenshot({ path: `e2e/shots/orders-${theme}.png`, fullPage: true });

    await page.goto(`/targets/${SCOPE}`);
    // Chờ số liệu chứ không chờ tiêu đề: tiêu đề là chữ tĩnh nên hiện ngay, ảnh sẽ chụp
    // đúng lúc mọi con số còn là dấu gạch.
    await expect(page.locator(".target-row").first()).toContainText("₫");
    await page.screenshot({ path: `e2e/shots/targets-${theme}.png`, fullPage: true });
  }
});
