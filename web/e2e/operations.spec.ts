import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

// Fixture có ngày cố định trong 03/2026, nên mọi trang báo cáo đều mở kèm start/end tường minh
// thay vì phụ thuộc tháng hiện tại.
const SAMPLE = resolve(__dirname, "..", "..", "tests", "fixtures", "affiliate_orders_e2e-sample.xlsx");
const ACCOUNT = "E2ESHOP";
const SCOPE = `?start=2026-03-01&end=2026-03-31&account=${ACCOUNT}`;

test("nhập file, đọc số liệu rồi hoàn tác lần nhập đó", async ({ page }) => {
  await test.step("tạo tài khoản", async () => {
    await page.goto("/accounts/");
    await page.getByLabel("Mã tài khoản").fill(ACCOUNT);
    await page.getByRole("button", { name: "Tạo tài khoản" }).click();
    await expect(page.getByText(`Đã tạo tài khoản ${ACCOUNT}.`)).toBeVisible();
  });

  await test.step("nhập file TikTok mẫu", async () => {
    await page.goto("/imports/");
    await page.getByLabel("Tài khoản TikTok").selectOption(ACCOUNT);
    await page.getByLabel("File Excel đã xuất từ TikTok").setInputFiles(SAMPLE);
    await page.getByRole("button", { name: "Nhập dữ liệu" }).click();
    const result = page.locator(".import-result");
    await expect(result).toHaveCount(1);
    await expect(result).toHaveAttribute("data-outcome", "imported");
    await expect(result).toContainText("2 dòng mới");
  });

  await test.step("dashboard hiện đúng tổng hoa hồng", async () => {
    await page.goto(`/${SCOPE}`);
    const commission = page.locator("article.pulse-metric", { hasText: "Hoa hồng thực tế" });
    await expect(commission.locator("strong")).toContainText("40.000");
  });

  await test.step("bảng đơn hàng có đúng 2 đơn", async () => {
    await page.goto(`/orders/${SCOPE}`);
    await expect(page.getByRole("heading", { level: 2 })).toContainText("2 đơn trong bộ lọc");
  });

  await test.step("hoàn tác lần nhập qua hộp xác nhận", async () => {
    await page.goto("/imports/");
    const importedBatch = page.locator("article.import-item", { hasText: ACCOUNT });
    await expect(importedBatch).toHaveCount(1);
    await importedBatch.getByRole("button", { name: "Hoàn tác lần nhập này" }).click();
    const dialog = page.locator("dialog.confirm-dialog[open]");
    await expect(dialog).toBeVisible();
    const phrase = await dialog.locator("label strong").innerText();
    await dialog.getByLabel(/Nhập chính xác/).fill(phrase);
    await dialog.getByRole("button", { name: "Hoàn tác lần nhập" }).click();
    await expect(page.getByRole("status")).toContainText("Đã hoàn tác");
  });

  await test.step("dữ liệu trở về rỗng", async () => {
    await page.goto(`/orders/${SCOPE}`);
    await expect(page.getByRole("heading", { level: 2 })).toContainText("0 đơn trong bộ lọc");
    await expect(page.getByText("Không có đơn phù hợp", { exact: false })).toBeVisible();
  });
});
