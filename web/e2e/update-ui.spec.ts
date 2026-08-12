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

test("lỗi updater chỉ hiện hướng xử lý tiếng Việt, không lộ chi tiết helper", async ({ page }) => {
  await page.route("**/api/v1/admin/update", async (route) => {
    await route.fulfill({
      json: {
        current_version: "2.0.3",
        latest_version: "2.0.4",
        available: true,
        installable: true,
        automatic_install_supported: true,
        release_name: "v2.0.4",
        release_url: "https://example.test/releases/v2.0.4",
        published_at: "2026-08-12T00:00:00Z",
        notes: null,
        source_repo: "example/updates",
      },
    });
  });
  await page.route("**/api/v1/admin/update/progress", async (route) => {
    await route.fulfill({
      json: {
        schema: "tiktok-affiliate-report.update-status.v1",
        phase: "failed",
        current_version: "2.0.3",
        target_version: "2.0.4",
        bytes_downloaded: 100,
        bytes_total: 100,
        percent: 100,
        error: "Không thể hoàn tất cài đặt bản cập nhật.",
        error_action: "Bấm “Thử lại” để tải lại gói. Nếu lỗi tiếp diễn, hãy liên hệ người hỗ trợ.",
        updated_at: "2026-08-12T00:00:00Z",
      },
    });
  });

  await page.goto("/settings/update/");

  const alert = page.locator(".update-message[data-tone='danger'][role='alert']");
  await expect(alert).toContainText("Không thể hoàn tất cài đặt bản cập nhật.");
  await expect(alert).toContainText("Việc cần làm:");
  await expect(alert).toContainText("Bấm “Thử lại” để tải lại gói.");
  await expect(page.getByRole("button", { name: "Thử lại" })).toBeVisible();
  await expect(page.getByText(/Installer exited|C:\\Users|updater-bootstrap/i)).toHaveCount(0);
});

async function offerUpdate(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/admin/update", async (route) => {
    await route.fulfill({
      json: {
        current_version: "2.0.7",
        latest_version: "2.0.8",
        available: true,
        installable: true,
        automatic_install_supported: true,
        release_name: "v2.0.8",
        release_url: "https://example.test/releases/v2.0.8",
        published_at: "2026-08-12T00:00:00Z",
        notes: null,
        source_repo: "example/updates",
      },
    });
  });
}

test("có bản mới thì mọi trang đều nhắc, và hoãn thì im cho tới bản kế tiếp", async ({ page }) => {
  await offerUpdate(page);

  await page.goto("/");
  const banner = page.locator(".update-banner");
  await expect(banner).toContainText("Có bản 2.0.8");

  // Nhắc ở mọi trang chứ không riêng Tổng quan — đó là cả lý do banner tồn tại.
  await page.goto("/orders/");
  await expect(page.locator(".update-banner")).toContainText("Có bản 2.0.8");

  // Trang Cập nhật đã nói đủ rồi, nhắc lại là thừa.
  await page.goto("/settings/update/");
  await expect(page.locator(".update-banner")).toHaveCount(0);

  await page.goto("/");
  await page.getByRole("button", { name: /Để sau/ }).click();
  await expect(page.locator(".update-banner")).toHaveCount(0);
  await page.goto("/orders/");
  await expect(page.locator(".update-banner")).toHaveCount(0);

  // Hoãn được ghi theo đúng phiên bản, nên bản kế tiếp vẫn phải nhắc lại.
  await page.evaluate(() => window.localStorage.setItem("tiktok-affiliate-update-postponed", "2.0.7"));
  await page.goto("/");
  await expect(page.locator(".update-banner")).toContainText("Có bản 2.0.8");
});

test("Cập nhật ngay mở thẳng hộp xác nhận và dọn hash khỏi địa chỉ", async ({ page }) => {
  await offerUpdate(page);
  // Cài tự động chỉ bật trên bản Windows đã đóng gói, nên môi trường test phải mượn capability
  // đó thì mới có nút Cài để hộp xác nhận bám vào.
  await page.route("**/api/v1/meta", async (route) => {
    const response = await route.fetch();
    const meta = await response.json();
    meta.capabilities.update_install = { available: true, reason: null };
    await route.fulfill({ json: meta });
  });

  await page.goto("/");
  await page.getByRole("link", { name: "Cập nhật ngay" }).click();

  await expect(page.locator("dialog.confirm-dialog[open]")).toContainText("Cài bản 2.0.8 ngay?");
  // Hash đã dùng xong thì phải dọn, không thì tải lại trang là hộp xác nhận bật lên lần nữa.
  expect(page.url()).not.toContain("#install");
});
