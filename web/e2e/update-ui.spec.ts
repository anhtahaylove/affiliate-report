import { expect, test, type Page } from "@playwright/test";
import type { UpdateProgress, UpdateStatus } from "../src/lib/api";
import { findClippedElements } from "./clipping";

const baseStatus: UpdateStatus = {
  current_version: "2.1.1",
  latest_version: "2.1.1",
  available: false,
  installable: true,
  automatic_install_supported: true,
  release_name: "v2.1.1",
  release_url: "https://example.test/releases/v2.1.1",
  published_at: "2026-08-14T11:50:00Z",
  notes: "Sửa trải nghiệm cập nhật.",
  source_repo: "example/updates",
  installer_name: "AffiliateReportSetup-v2.1.1.exe",
  installer_size: 46_020_826,
  bootstrap_version: "1.0.0",
};

const baseProgress: UpdateProgress = {
  schema: "tiktok-affiliate-report.update-status.v1",
  phase: "idle",
  current_version: "2.1.1",
  target_version: null,
  bytes_downloaded: 0,
  bytes_total: 0,
  percent: null,
  error: null,
  error_action: null,
  updated_at: null,
};

async function enableWindowsInstall(page: Page) {
  await page.route("**/api/v1/meta", async (route) => {
    const response = await route.fetch();
    const meta = await response.json();
    meta.capabilities.update_check = { available: true, reason: null };
    meta.capabilities.update_install = { available: true, reason: null };
    await route.fulfill({ json: meta });
  });
}

async function mockUpdate(page: Page, status: UpdateStatus = baseStatus, progress: UpdateProgress = baseProgress) {
  await page.route("**/api/v1/admin/update", (route) => route.fulfill({ json: status }));
  await page.route("**/api/v1/admin/update/progress", (route) => route.fulfill({ json: progress }));
}

test("progress cũ thấp hơn current không còn giả làm bản mới nhất sau reload hoặc back", async ({ page }) => {
  await mockUpdate(page, { ...baseStatus, latest_version: "2.0.29", release_name: "v2.0.29" }, {
    ...baseProgress,
    current_version: "2.0.29",
    phase: "installed",
    target_version: "2.0.29",
    bytes_downloaded: 46_020_826,
    bytes_total: 46_020_826,
    percent: 100,
    updated_at: "2026-08-13T15:48:12Z",
  });

  for (const viewport of [{ width: 320, height: 720 }, { width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1440, height: 900 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/settings/update/");
    await expect(page.getByRole("heading", { name: "Bạn đang dùng bản mới nhất" })).toBeVisible();
    await expect(page.locator(".update-version-grid")).toContainText("2.1.1");
    await expect(page.locator(".update-version-grid")).toContainText("Không có bản mới hơn");
    await expect(page.locator(".update-stages")).toHaveCount(0);
    await expect(page.locator("#update-download-progress")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  }

  await page.goto("/orders/");
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Bạn đang dùng bản mới nhất" })).toBeVisible();
  await expect(page.locator(".update-stages")).toHaveCount(0);
});

test("trạng thái checking không nhấp nháy thành latest trước khi API trả lời", async ({ page }) => {
  let releaseStatus!: () => void;
  const waitForRelease = new Promise<void>((resolve) => { releaseStatus = resolve; });
  await page.route("**/api/v1/admin/update", async (route) => {
    await waitForRelease;
    await route.fulfill({ json: baseStatus });
  });
  await page.route("**/api/v1/admin/update/progress", (route) => route.fulfill({ json: baseProgress }));

  await page.goto("/settings/update/");
  await expect(page.getByRole("heading", { name: "Đang kiểm tra phiên bản" })).toBeVisible();
  releaseStatus();
  await expect(page.getByRole("heading", { name: "Bạn đang dùng bản mới nhất" })).toBeVisible();
});

test("bản mới tự động có version delta và một CTA cài đặt chính", async ({ page }) => {
  await enableWindowsInstall(page);
  await mockUpdate(page, { ...baseStatus, latest_version: "2.1.2", available: true, release_name: "v2.1.2" });
  await page.goto("/settings/update/");

  await expect(page.getByRole("heading", { name: "Bản 2.1.2 đã sẵn sàng" })).toBeVisible();
  await expect(page.getByLabel("Nâng từ phiên bản 2.1.1 lên 2.1.2")).toBeVisible();
  await expect(page.getByRole("button", { name: "Tải và cài bản 2.1.2" })).toBeVisible();
  await expect(page.getByText(/Gói cài Windows · 43[,.]9 MB/)).toBeVisible();
  await expect(page.locator(".update-stages")).toHaveCount(0);
});

test("bản mới không hỗ trợ auto-install dẫn tới trang tải thủ công", async ({ page }) => {
  await mockUpdate(page, { ...baseStatus, latest_version: "2.1.2", available: true, automatic_install_supported: false, release_name: "v2.1.2" });
  await page.goto("/settings/update/");
  await expect(page.getByRole("heading", { name: "Có bản 2.1.2 để tải" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Mở trang tải" })).toBeVisible();
});

for (const scenario of [
  { phase: "downloading", percent: 0 },
  { phase: "downloading", percent: 35 },
  { phase: "downloading", percent: 100 },
  { phase: "verifying", percent: 100 },
  { phase: "installing", percent: 100 },
  { phase: "restarting", percent: 100 },
] as const) {
  test(`phase ${scenario.phase} ${scenario.percent}% chỉ hiện progress tải khi phù hợp`, async ({ page }) => {
    await mockUpdate(page, { ...baseStatus, latest_version: "2.1.2", available: true, release_name: "v2.1.2" }, {
      ...baseProgress,
      phase: scenario.phase,
      target_version: "2.1.2",
      bytes_downloaded: Math.round(1_000 * scenario.percent / 100),
      bytes_total: 1_000,
      percent: scenario.percent,
      updated_at: "2026-08-14T11:59:30Z",
    });
    await page.goto("/settings/update/");
    await expect(page.locator(".update-stages li")).toHaveCount(5);
    await expect(page.locator("#update-download-progress")).toHaveCount(scenario.phase === "downloading" ? 1 : 0);
    if (scenario.phase === "downloading") {
      await expect(page.locator("#update-download-progress")).toBeVisible();
    }
    // Có mặt trong DOM chưa đủ. Vòng quét route trong layout-audit không bao giờ chạm tới
    // các trạng thái này, mà v2.1.2 hỏng đúng ở trạng thái downloading — nên phải quét ở đây.
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await findClippedElements(page), `phase ${scenario.phase} @${width}`).toEqual([]);
    }
  });
}

test("offline có recovery action riêng", async ({ page }) => {
  await page.route("**/api/v1/admin/update", (route) => route.abort("connectionrefused"));
  await page.route("**/api/v1/admin/update/progress", (route) => route.fulfill({ json: baseProgress }));
  await page.goto("/settings/update/");
  await expect(page.getByRole("heading", { name: "Chưa thể kiểm tra cập nhật" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Thử lại" })).toBeVisible();
});

test("lỗi chữ ký, hash hoặc installer chỉ hiện hướng xử lý tiếng Việt, không lộ chi tiết helper", async ({ page }) => {
  await mockUpdate(page, { ...baseStatus, latest_version: "2.1.2", available: true, release_name: "v2.1.2" }, {
    ...baseProgress,
    phase: "failed",
    target_version: "2.1.2",
    bytes_downloaded: 100,
    bytes_total: 100,
    percent: 100,
    error: "Không thể hoàn tất cài đặt bản cập nhật.",
    error_action: "Bấm “Thử lại” để tải lại gói. Nếu lỗi tiếp diễn, hãy liên hệ người hỗ trợ.",
    updated_at: "2026-08-14T11:59:30Z",
  });

  await page.goto("/settings/update/");
  const alert = page.locator(".update-message[data-tone='danger'][role='alert']");
  await expect(alert).toContainText("Không thể hoàn tất cài đặt bản cập nhật.");
  await expect(alert).toContainText("Việc cần làm:");
  await expect(page.getByRole("button", { name: "Thử lại" })).toBeVisible();
  await expect(page.getByText(/Installer exited|C:\\Users|updater-bootstrap|token=/i)).toHaveCount(0);
});

for (const failure of [
  {
    name: "signature-hash",
    message: "Không thể xác minh tính toàn vẹn của gói cập nhật.",
    action: "Bấm “Thử lại” để tải lại gói từ nguồn phát hành đã ký.",
  },
  {
    name: "installer",
    message: "Bộ cài không thể hoàn tất cập nhật.",
    action: "Mở trang phát hành để cài thủ công hoặc liên hệ người hỗ trợ.",
  },
] as const) {
  test(`lỗi ${failure.name} có recovery action đã sanitize`, async ({ page }) => {
    await mockUpdate(page, { ...baseStatus, latest_version: "2.1.2", available: true, release_name: "v2.1.2" }, {
      ...baseProgress,
      phase: "failed",
      target_version: "2.1.2",
      error: failure.message,
      error_action: failure.action,
      updated_at: "2026-08-14T11:59:30Z",
    });
    await page.goto("/settings/update/");
    await expect(page.getByRole("heading", { name: "Cập nhật gặp sự cố" })).toBeVisible();
    const alert = page.locator(".update-message[role='alert']");
    await expect(alert).toContainText(failure.message);
    await expect(alert).toContainText(failure.action);
    await expect(page.getByText(/C:\\|\/Users\/|token=|Traceback|exit code/i)).toHaveCount(0);
  });
}

test("installed vừa hoàn tất chỉ hiện timeline ngắn hạn và không hiện progress tải 100%", async ({ page }) => {
  const now = new Date().toISOString();
  await mockUpdate(page, { ...baseStatus, current_version: "2.1.2", latest_version: "2.1.2", release_name: "v2.1.2" }, {
    ...baseProgress,
    phase: "installed",
    current_version: "2.1.2",
    target_version: "2.1.2",
    bytes_downloaded: 46_020_826,
    bytes_total: 46_020_826,
    percent: 100,
    updated_at: now,
  });
  await page.goto("/settings/update/");
  await expect(page.locator(".update-state").getByRole("heading", { name: "Đã cài xong bản 2.1.2" })).toBeVisible();
  await expect(page.locator(".update-stages li")).toHaveCount(5);
  await expect(page.locator("#update-download-progress")).toHaveCount(0);
});

test("mất kết nối dự kiến sau khi chạy installer chuyển sang reconnecting", async ({ page }) => {
  await enableWindowsInstall(page);
  let updateStarted = false;
  await page.route("**/api/v1/admin/update", (route) => route.fulfill({ json: { ...baseStatus, latest_version: "2.1.2", available: true, release_name: "v2.1.2" } }));
  await page.route("**/api/v1/admin/update/progress", (route) => updateStarted ? route.abort("connectionrefused") : route.fulfill({ json: baseProgress }));
  await page.route("**/api/v1/admin/update/install", (route) => {
    updateStarted = true;
    return route.fulfill({ json: { version: "2.1.2", status: "scheduled", release_url: baseStatus.release_url } });
  });

  await page.goto("/settings/update/");
  await page.getByRole("button", { name: "Tải và cài bản 2.1.2" }).click();
  const dialog = page.getByRole("dialog", { name: "Cài bản 2.1.2 ngay?" });
  await dialog.getByRole("button", { name: "Cài bản cập nhật" }).click();
  await expect(page.getByRole("heading", { name: "Đang chờ ứng dụng kết nối lại" })).toBeVisible();
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
  await page.route("**/api/v1/admin/update/progress", async (route) => {
    await route.fulfill({ json: { ...baseProgress, current_version: "2.0.7" } });
  });
}

test("có bản mới thì mọi trang đều nhắc, và hoãn thì im cho tới bản kế tiếp", async ({ page }) => {
  await offerUpdate(page);

  await page.goto("/");
  const banner = page.getByRole("status", { name: "Thông báo cập nhật ứng dụng" });
  await expect(banner).toContainText("Có bản 2.0.8");

  // Nhắc ở mọi trang chứ không riêng Tổng quan — đó là cả lý do banner tồn tại.
  await page.goto("/orders/");
  await expect(page.getByRole("status", { name: "Thông báo cập nhật ứng dụng" })).toContainText("Có bản 2.0.8");

  // Trang Cập nhật đã nói đủ rồi, nhắc lại là thừa.
  await page.goto("/settings/update/");
  await expect(page.getByRole("status", { name: "Thông báo cập nhật ứng dụng" })).toHaveCount(0);

  await page.goto("/");
  await page.getByRole("button", { name: /Để sau/ }).click();
  await expect(page.getByRole("status", { name: "Thông báo cập nhật ứng dụng" })).toHaveCount(0);
  await page.goto("/orders/");
  await expect(page.getByRole("status", { name: "Thông báo cập nhật ứng dụng" })).toHaveCount(0);

  // Hoãn được ghi theo đúng phiên bản, nên bản kế tiếp vẫn phải nhắc lại.
  await page.evaluate(() => window.localStorage.setItem("tiktok-affiliate-update-postponed", "2.0.7"));
  await page.goto("/");
  await expect(page.getByRole("status", { name: "Thông báo cập nhật ứng dụng" })).toContainText("Có bản 2.0.8");
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
