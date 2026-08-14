import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const dashboardLayout = {
  schema: 1,
  order: ["today_pulse", "target_progress", "action_alerts", "trend", "account_contribution", "settlement", "data_freshness", "recent_imports"],
  hidden: [],
};

async function mockShell(page: Page, platform: "windows" | "android" = "windows") {
  // Giữ desktop token trong fixture Android để chứng minh capability nền tảng thắng dữ liệu auth cũ.
  await page.route("**/auth/me", (route) => route.fulfill({ json: { email: "local-owner@localhost", role: "owner", accounts: [], auth_method: "local", desktop_app: true, desktop_control_token: "test-token" } }));
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({ json: { theme: "system", sidebar_collapsed: false, dashboard_layout: dashboardLayout, updated_at: null } }));
  await page.route("**/api/v1/meta", (route) => route.fulfill({
    json: {
      accounts: [], account_items: [], statuses: [], max_upload_mb: 50, app_version: "2.1.0", runtime_platform: platform,
      capabilities: {
        database_backend: "sqlite", auth_mode: "local",
        data_admin: { available: true, reason: null },
        sync: { available: true, reason: null },
        update_check: { available: platform === "windows", reason: platform === "android" ? "Không dùng updater Windows trên Android." : null },
        update_install: { available: platform === "windows", reason: platform === "android" ? "Không dùng installer Windows trên Android." : null },
        android_update: { available: platform === "android", reason: null },
      },
      android_update: platform === "android" ? { current_version: "2.1.0", latest_version: "2.1.1", available: true, installable: true, release_url: "https://example.test/v2.1.1", message: "APK đã sẵn sàng." } : null,
      identity_policy: { mode: "local", oidc_allowlist_enforced: false, enforcement: "local_owner" },
    },
  }));
}

async function installAndroidDownloadBridge(page: Page) {
  await page.addInitScript(() => {
    const downloads: Array<{ url: string; filename: string; mimeType: string }> = [];
    Object.assign(window, {
      __affiliateReportNativeDownloads: downloads,
      AffiliateReportAndroid: {
        download(url: string, filename: string, mimeType: string) {
          downloads.push({ url, filename, mimeType });
        },
      },
    });
  });
}

test("wizard .affsync export, preview xung đột và xác nhận import", async ({ page }) => {
  await mockShell(page);
  let importBody: Record<string, unknown> | null = null;
  await page.route("**/api/v1/sync/status", (route) => route.fulfill({ json: { schema: 1, device: { device_id: "desktop-1", device_name: "Máy văn phòng", platform: "windows" }, max_package_bytes: 104857600, history_count: 0 } }));
  await page.route("**/api/v1/sync/history", (route) => route.fulfill({ json: { items: [], count: 0 } }));
  await page.route("**/api/v1/sync/export", (route) => route.fulfill({ body: "AFFSYNC1-test", headers: { "content-type": "application/octet-stream", "content-disposition": "attachment; filename=AffiliateReport-test.affsync" } }));
  await page.route("**/api/v1/sync/preview", (route) => {
    expect(route.request().postDataBuffer()?.toString("latin1")).toContain('name="package"');
    return route.fulfill({ json: {
      preview_id: "preview-1", expires_at: "2026-08-14T12:15:00Z", duplicate: false,
      manifest: {
        package_id: "package-1", exported_at: "2026-08-14T12:00:00Z",
        source_device: { device_id: "phone-1", device_name: "Điện thoại", platform: "android" }, counts: { import_batches: 2, raw_rows: 15 },
      },
      summary: { new_import_batches: 2, new_raw_rows: 15 },
      conflicts: [{ key: "account:SHOP", entity: "account", label: "Tên tài khoản SHOP", local: "Shop máy tính", incoming: "Shop điện thoại", default: "local" }],
    } });
  });
  await page.route("**/api/v1/sync/import", async (route) => {
    importBody = route.request().postDataJSON();
    await route.fulfill({ json: { duplicate: false, changed: true, package_id: "package-1", backup_path: "backup-before-sync.db", applied: { import_batches: 2, raw_rows: 15 }, rebuilt: { lines: 15 } } });
  });

  await page.goto("/settings/sync/");
  await expect(page.getByRole("heading", { name: "Chuyển dữ liệu an toàn giữa các thiết bị" })).toBeVisible();
  await expect(page.getByText("Máy văn phòng")).toBeVisible();

  await page.getByRole("button", { name: "Tạo mật khẩu" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Xuất file .affsync" }).click();
  expect((await download).suggestedFilename()).toBe("AffiliateReport-test.affsync");

  await page.getByLabel("File đồng bộ").setInputFiles({ name: "phone.affsync", mimeType: "application/octet-stream", buffer: Buffer.from("AFFSYNC1-test") });
  await page.getByLabel("Mật khẩu mở gói").fill("mat-khau-rat-dai");
  await page.getByRole("button", { name: "Mở và xem trước" }).click();
  await expect(page.getByRole("heading", { name: "Ảnh hưởng của gói" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Còn 1 xung đột/ })).toBeDisabled();
  await page.getByLabel("Cách xử lý").selectOption("local");
  await page.getByRole("button", { name: "Tiếp tục đồng bộ" }).click();
  const dialog = page.getByRole("dialog", { name: "Hợp nhất dữ liệu từ gói này?" });
  await dialog.getByLabel(/Nhập chính xác/).fill("DONG BO");
  await dialog.getByRole("button", { name: "Đồng bộ dữ liệu" }).click();
  await expect(page.getByText(/Đồng bộ hoàn tất/)).toBeVisible();
  expect(importBody).toEqual({ preview_id: "preview-1", confirmation: "DONG BO", conflict_resolutions: { "account:SHOP": "local" } });

  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(axe.violations).toEqual([]);
});

test("Android chỉ hiển thị trạng thái APK và không gọi updater Windows", async ({ page }) => {
  await mockShell(page, "android");
  await installAndroidDownloadBridge(page);
  let windowsUpdaterCalls = 0;
  let prepareCalls = 0;
  let packageGetCalls = 0;
  await page.route("**/api/v1/update/android/status", (route) => route.fulfill({ json: { current_version: "2.1.0", latest_version: "2.1.1", available: true, installable: true, release_url: "https://example.test/v2.1.1", message: "APK đã sẵn sàng." } }));
  await page.route("**/api/v1/admin/update**", (route) => { windowsUpdaterCalls += 1; return route.fulfill({ status: 500 }); });
  await page.route("**/api/v1/update/android/prepare", (route) => {
    prepareCalls += 1;
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["x-csrf-token"]).toBe("test-csrf");
    return route.fulfill({ json: { download_url: "/api/v1/update/android/download/test-apk", filename: "AffiliateReport-v2.1.1-arm64.apk", version: "2.1.1", size: 12, sha256: "A".repeat(64) } });
  });
  await page.route("**/api/v1/update/android/download/test-apk", (route) => { packageGetCalls += 1; return route.fulfill({ status: 500 }); });
  await page.goto("/settings/update/");
  await page.evaluate(() => { document.cookie = "csrf_token=test-csrf; path=/"; });
  await expect(page.locator('meta[name="viewport"]')).toHaveAttribute("content", /viewport-fit=cover/);
  await expect(page.getByRole("heading", { name: "Có APK 2.1.1 sẵn sàng" })).toBeVisible();
  await expect(page.getByText("Không chạy installer Windows")).toBeVisible();
  await page.getByRole("button", { name: "Tải và cài APK" }).click();
  await expect.poll(() => page.evaluate(() => (window as Window & { __affiliateReportNativeDownloads?: unknown[] }).__affiliateReportNativeDownloads?.length ?? 0)).toBe(1);
  expect(await page.evaluate(() => (window as Window & { __affiliateReportNativeDownloads?: Array<Record<string, string>> }).__affiliateReportNativeDownloads?.[0])).toMatchObject({
    filename: "AffiliateReport-v2.1.1-arm64.apk",
    mimeType: "application/vnd.android.package-archive",
  });
  await expect(page.getByText(/đã được xác minh và chuyển sang trình cài đặt Android/)).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("affiliate-report-apk-ready", {
    detail: { version: "2.1.1", size: 12, sha256: "A".repeat(64) },
  })));
  await expect(page.getByText(/đã được xác minh và chuyển sang trình cài đặt Android/)).toBeVisible();
  expect(prepareCalls).toBe(1);
  expect(packageGetCalls).toBe(0);
  await expect(page.getByRole("button", { name: "Thoát ứng dụng" })).toHaveCount(0);
  expect(windowsUpdaterCalls).toBe(0);
  await expect(page.getByText("Cục bộ trên Android")).toBeVisible();
});

test("Android xuất .affsync qua URL loopback một lần thay vì Blob URL", async ({ page }) => {
  await mockShell(page, "android");
  await installAndroidDownloadBridge(page);
  let prepareCalls = 0;
  let legacyBlobCalls = 0;
  let packageGetCalls = 0;
  await page.route("**/api/v1/sync/status", (route) => route.fulfill({ json: { schema: 1, device: { device_id: "phone-1", device_name: "Điện thoại", platform: "android" }, max_package_bytes: 104857600, history_count: 0 } }));
  await page.route("**/api/v1/sync/history", (route) => route.fulfill({ json: { items: [], count: 0 } }));
  await page.route("**/api/v1/sync/export/prepare", (route) => {
    prepareCalls += 1;
    expect(route.request().postDataJSON()).toMatchObject({ passphrase: expect.any(String) });
    return route.fulfill({ json: {
      download_url: "/api/v1/sync/export/download/one-time",
      filename: "AffiliateReport-android.affsync",
      size: 13,
      expires_at: "2026-08-14T12:05:00Z",
    } });
  });
  await page.route("**/api/v1/sync/export/download/one-time", (route) => { packageGetCalls += 1; return route.fulfill({ status: 500 }); });
  await page.route("**/api/v1/sync/export", (route) => { legacyBlobCalls += 1; return route.fulfill({ status: 500 }); });

  await page.goto("/settings/sync/");
  await page.evaluate(() => { document.cookie = "csrf_token=test-csrf; path=/"; });
  await page.getByRole("button", { name: "Tạo mật khẩu" }).click();
  await page.getByRole("button", { name: "Xuất file .affsync" }).click();
  await expect.poll(() => page.evaluate(() => (window as Window & { __affiliateReportNativeDownloads?: unknown[] }).__affiliateReportNativeDownloads?.length ?? 0)).toBe(1);
  expect(await page.evaluate(() => (window as Window & { __affiliateReportNativeDownloads?: Array<Record<string, string>> }).__affiliateReportNativeDownloads?.[0])).toMatchObject({
    filename: "AffiliateReport-android.affsync",
    mimeType: "application/vnd.affiliate-report.sync",
  });
  await expect(page.getByText(/Đã lưu AffiliateReport-android.affsync/)).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("affiliate-report-download-ready", {
    detail: { source: new URL("/api/v1/sync/export/download/one-time", window.location.origin).toString(), size: 13 },
  })));
  await expect(page.getByText(/Đã lưu AffiliateReport-android.affsync/)).toBeVisible();
  expect(prepareCalls).toBe(1);
  expect(legacyBlobCalls).toBe(0);
  expect(packageGetCalls).toBe(0);
});
