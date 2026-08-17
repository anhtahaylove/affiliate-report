import { expect, test } from "@playwright/test";
import type { PairingStatus } from "../src/lib/api";

const ACCOUNT = "PAIRSHOP";
const QR = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M0 0h10v10H0z"/></svg>';

test("chọn rõ LAN hoặc Cloud và cloud không lộ URL capability", async ({ page }) => {
  await page.goto("/accounts/");
  await page.getByLabel("Mã tài khoản").fill(ACCOUNT);
  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await expect(page.getByText(`Đã tạo tài khoản ${ACCOUNT}.`)).toBeVisible();

  let status: PairingStatus = { enabled: false, so_lan_nhan: 0 };
  await page.route("**/api/v1/pairing", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      const mode = (await request.postDataBuffer())?.toString().includes("cloud") ? "cloud" : "lan";
      status = {
        enabled: true,
        mode,
        account: ACCOUNT,
        qr_svg: QR,
        expires_in: 300,
        so_lan_nhan: 0,
        phase: "created",
        message: "Đang chờ điện thoại chọn file.",
        ...(mode === "cloud" ? { relay_host: "aff-report.huuhungn.io.vn" } : { url: "http://192.168.1.20:8765/pair/token" }),
      };
    } else if (request.method() === "DELETE") {
      status = { enabled: false, so_lan_nhan: 0 };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status) });
  });

  await page.goto("/imports/");
  await page.getByLabel("Tài khoản TikTok").selectOption(ACCOUNT);
  await expect(page.getByRole("group", { name: "Chọn cách kết nối" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Cùng Wi-Fi/ })).toBeVisible();
  await page.getByRole("button", { name: /Khác mạng/ }).click();

  await expect(page.getByText("Khác mạng")).toBeVisible();
  await expect(page.getByText("Đường truyền: đã mã hóa qua máy chủ trung chuyển")).toBeVisible();
  await expect(page.getByText(/http.*pair/i)).toHaveCount(0);
  await expect(page.locator(".pairing-qr svg")).toBeVisible();

  await page.getByRole("button", { name: "Tắt ghép cặp" }).click();
  await expect(page.getByRole("group", { name: "Chọn cách kết nối" })).toBeVisible();
});

for (const mode of ["lan", "cloud"] as const) {
  test(`hiện cảnh báo overlap sau khi nhận file qua ${mode.toUpperCase()}`, async ({ page }) => {
    const account = mode === "lan" ? "PAIRWARNLAN" : "PAIRWARNCLOUD";
    await page.goto("/accounts/");
    await page.getByLabel("Mã tài khoản").fill(account);
    await page.getByRole("button", { name: "Tạo tài khoản" }).click();
    await expect(page.getByText(`Đã tạo tài khoản ${account}.`)).toBeVisible();

    let status: PairingStatus = { enabled: false, so_lan_nhan: 0 };
    await page.route("**/api/v1/pairing", async (route) => {
      if (route.request().method() === "POST") {
        status = {
          enabled: true,
          mode,
          account,
          qr_svg: QR,
          expires_in: 300,
          so_lan_nhan: 0,
          phase: "created",
          message: "Đang chờ điện thoại chọn file.",
          ...(mode === "cloud"
            ? { relay_host: "aff-report.huuhungn.io.vn" }
            : { url: "http://192.168.1.20:8765/pair/token" }),
        };
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(status) });
    });

    await page.goto("/imports/");
    await page.getByLabel("Tài khoản TikTok").selectOption(account);
    await page.getByRole("button", { name: mode === "cloud" ? /Khác mạng/ : /Cùng Wi-Fi/ }).click();
    await expect(page.locator(".pairing-qr svg")).toBeVisible();

    status = {
      enabled: false,
      mode,
      account,
      so_lan_nhan: 1,
      phase: "idle",
      message: "Đã nhận và nhập file từ điện thoại.",
      result: {
        inserted: 25,
        warnings: [
          {
            code: "cross_account_overlap",
            severity: "warning",
            other_account: "SHOP1",
            overlap_count: 24,
            incoming_count: 25,
            overlap_ratio: 0.96,
            message: "24/25 đơn và SKU đã có trong SHOP1.",
          },
        ],
      },
    };

    const warning = page.locator(".pairing-panel .import-overlap-warning");
    await expect(warning).toBeVisible({ timeout: 10_000 });
    await expect(warning).toContainText("Cảnh báo dữ liệu có thể bị gắn nhầm tài khoản");
    await expect(warning).toContainText("24/25 đơn và SKU đã có trong SHOP1.");
    await expect(warning).toContainText("Hãy kiểm tra tài khoản đang chọn");
  });
}
