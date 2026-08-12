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
