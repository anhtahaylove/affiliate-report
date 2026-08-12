import { expect, test } from "@playwright/test";


test("service worker dùng app version, cache đủ shell và không fallback nhầm Dashboard", async ({ context, page, request }) => {
  const metaResponse = await request.get("/api/v1/meta");
  expect(metaResponse.ok()).toBeTruthy();
  const meta = await metaResponse.json() as { app_version: string };

  const workerResponse = await request.get("/sw.js");
  expect(workerResponse.ok()).toBeTruthy();
  expect(workerResponse.headers()["cache-control"]).toBe("no-cache, no-store, must-revalidate");
  const workerSource = await workerResponse.text();
  expect(workerSource).toContain(`const CACHE = \`\${CACHE_PREFIX}${meta.app_version}\`;`);
  expect(workerSource).not.toContain("__APP_VERSION__");

  await page.goto("/");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  expect(await page.evaluate(async () => (await navigator.serviceWorker.ready).updateViaCache)).toBe("none");
  if (!await page.evaluate(() => Boolean(navigator.serviceWorker.controller))) {
    await page.reload();
  }
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);

  const cacheState = await page.evaluate(async () => ({
    keys: await caches.keys(),
    preferences: Boolean(await caches.match("/settings/preferences/")),
    offline: Boolean(await caches.match("/offline.html")),
  }));
  expect(cacheState.keys).toContain(`tiktok-affiliate-report-shell-${meta.app_version}`);
  expect(cacheState.preferences).toBe(true);
  expect(cacheState.offline).toBe(true);

  await context.setOffline(true);
  try {
    await page.goto("/route-chua-cache/", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Ứng dụng đang kết nối lại" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tổng quan hiệu suất" })).toHaveCount(0);
  } finally {
    await context.setOffline(false);
  }
});
