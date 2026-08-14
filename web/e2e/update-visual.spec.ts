import { expect, test, type Page } from "@playwright/test";
import type { UpdateProgress, UpdateStatus } from "../src/lib/api";

const baseStatus: UpdateStatus = {
  current_version: "2.1.1",
  latest_version: "2.1.1",
  available: false,
  installable: true,
  automatic_install_supported: true,
  release_name: "v2.1.1",
  release_url: "https://example.test/releases/v2.1.1",
  published_at: "2026-08-14T11:50:00Z",
  notes: "Cải thiện trải nghiệm cập nhật và độ rõ ràng của trạng thái.",
  source_repo: "anhtahaylove/affiliate-report-updates",
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

const states = {
  latest: { status: baseStatus, progress: baseProgress, heading: "Bạn đang dùng bản mới nhất" },
  available: {
    status: { ...baseStatus, latest_version: "2.1.2", available: true, release_name: "v2.1.2" },
    progress: baseProgress,
    heading: "Bản 2.1.2 đã sẵn sàng",
  },
  active: {
    status: { ...baseStatus, latest_version: "2.1.2", available: true, release_name: "v2.1.2" },
    progress: { ...baseProgress, phase: "installing", target_version: "2.1.2", bytes_downloaded: 46_020_826, bytes_total: 46_020_826, percent: 100, updated_at: "2026-08-14T12:00:00Z" },
    heading: "Đang cài đặt",
  },
  error: {
    status: { ...baseStatus, latest_version: "2.1.2", available: true, release_name: "v2.1.2" },
    progress: { ...baseProgress, phase: "failed", target_version: "2.1.2", error: "Không thể hoàn tất cài đặt bản cập nhật.", error_action: "Bấm “Thử lại” để tải lại gói.", updated_at: "2026-08-14T12:00:00Z" },
    heading: "Cập nhật gặp sự cố",
  },
} satisfies Record<string, { status: UpdateStatus; progress: UpdateProgress; heading: string }>;

async function enableWindowsUpdater(page: Page) {
  await page.route("**/api/v1/meta", async (route) => {
    const response = await route.fetch();
    const meta = await response.json();
    meta.capabilities.update_check = { available: true, reason: null };
    meta.capabilities.update_install = { available: true, reason: null };
    await route.fulfill({ json: meta });
  });
}

test("@shots bằng chứng Update latest/available/active/error ở light, dark và mobile", async ({ page }) => {
  let theme: "light" | "dark" = "light";
  let selected = states.latest;
  await enableWindowsUpdater(page);
  await page.route("**/api/v1/ui/preferences", (route) => route.fulfill({
    json: { theme, sidebar_collapsed: false, dashboard_layout: null, updated_at: null },
  }));
  await page.route("**/api/v1/admin/update", (route) => route.fulfill({ json: selected.status }));
  await page.route("**/api/v1/admin/update/progress", (route) => route.fulfill({ json: selected.progress }));

  for (const [name, state] of Object.entries(states)) {
    selected = state;
    for (const nextTheme of ["light", "dark"] as const) {
      theme = nextTheme;
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto("/settings/update/");
      await expect(page.getByRole("heading", { name: state.heading, exact: true })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", nextTheme);
      await page.screenshot({ path: `e2e/shots/update-${name}-${nextTheme}-1440.png`, fullPage: true });
    }
  }

  for (const [name, state] of Object.entries(states)) {
    selected = state;
    theme = "light";
    const width = name === "latest" ? 320 : 390;
    await page.setViewportSize({ width, height: name === "latest" ? 720 : 844 });
    await page.goto("/settings/update/");
    await expect(page.getByRole("heading", { name: state.heading, exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    await page.screenshot({ path: `e2e/shots/update-${name}-mobile-${width}.png`, fullPage: true });
  }
});
