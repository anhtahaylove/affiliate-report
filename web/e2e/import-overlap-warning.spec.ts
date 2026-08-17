import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const SAMPLE = resolve(__dirname, "..", "..", "tests", "fixtures", "affiliate_orders_e2e-sample.xlsx");
const SOURCE = "OVERLAPSOURCE";
const TARGET = "OVERLAPTARGET";

async function createAccount(page: import("@playwright/test").Page, code: string) {
  await page.goto("/accounts/");
  await page.getByLabel("Mã tài khoản").fill(code);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await expect(page.getByText(`Đã tạo tài khoản ${code}.`)).toBeVisible();
}

async function importSample(page: import("@playwright/test").Page, account: string) {
  await page.goto("/imports/");
  await page.getByLabel("Tài khoản TikTok").selectOption(account);
  await page.getByLabel("File Excel đã xuất từ TikTok").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Nhập dữ liệu" }).click();
  await expect(page.locator(".import-result")).toHaveCount(1);
}

test("cảnh báo khi cùng order và SKU bị nhập vào hai account", async ({ page }) => {
  await createAccount(page, SOURCE);
  await createAccount(page, TARGET);
  await importSample(page, SOURCE);

  await importSample(page, TARGET);
  const warning = page.locator(".import-overlap-warning");
  await expect(warning).toContainText("Cảnh báo dữ liệu có thể bị gắn nhầm tài khoản");
  await expect(warning).toContainText(`2/2 dòng đơn hàng + SKU (100,0%) cũng đang tồn tại trong ${SOURCE}`);
  await expect(warning).toContainText("File vẫn được nhập để không làm mất dữ liệu");
});
