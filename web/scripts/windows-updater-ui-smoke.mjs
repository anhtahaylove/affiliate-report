import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.env.UPDATER_BASE_URL;
const previousVersion = process.env.PREVIOUS_VERSION;
const currentVersion = process.env.CURRENT_VERSION;
const evidenceDir = process.env.UPDATER_EVIDENCE_DIR;

if (!baseUrl || !previousVersion || !currentVersion || !evidenceDir) {
  throw new Error("Missing updater UI smoke environment.");
}

await mkdir(evidenceDir, { recursive: true });

function sanitizedError(reason) {
  const message = reason instanceof Error ? reason.message : String(reason);
  return message
    .replace(/[A-Za-z]:\\[^\r\n]+/g, "[local path]")
    .replace(/(token|secret|authorization)=?[^\s&]*/gi, "$1=[redacted]")
    .slice(0, 2000);
}

async function getJson(path, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "request not attempted";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}${path}`);
      if (response.ok) return await response.json();
      lastError = `HTTP ${response.status}`;
    } catch (reason) {
      lastError = sanitizedError(reason);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Timed out waiting for ${path}: ${lastError}`);
}

async function observeDisconnectAndRecovery(timeoutMs = 300_000) {
  const startedAt = Date.now();
  const deadline = startedAt + timeoutMs;
  let disconnectedAt = null;

  while (Date.now() < deadline) {
    let healthy = false;
    try {
      const response = await fetch(`${baseUrl}/health?updater_smoke=${Date.now()}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(1_000),
      });
      healthy = response.ok;
    } catch {
      healthy = false;
    }

    if (!healthy && disconnectedAt === null) disconnectedAt = Date.now();
    if (healthy && disconnectedAt !== null) {
      const recoveredAt = Date.now();
      return {
        disconnected_at: new Date(disconnectedAt).toISOString(),
        recovered_at: new Date(recoveredAt).toISOString(),
        outage_ms: recoveredAt - disconnectedAt,
      };
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  if (disconnectedAt === null) throw new Error("Updater never produced an observable application disconnect.");
  throw new Error("Application disconnected for the updater but did not recover before timeout.");
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
let step = "open-update-page";

try {
  await page.goto(`${baseUrl}/settings/update/`, { waitUntil: "domcontentloaded" });
  step = "check-update";
  await page.getByRole("button", { name: "Kiểm tra lại" }).click();

  step = "confirm-target-version";
  const installButton = page.getByRole("button", { name: `Cài bản ${currentVersion}` });
  await installButton.waitFor({ state: "visible", timeout: 90_000 });
  const previousVisible = await page.getByText(previousVersion, { exact: true }).count();
  if (previousVisible < 1) throw new Error("Previous version is not visible before update.");

  step = "start-install-from-ui";
  await installButton.click();
  await page.getByRole("button", { name: "Cài bản cập nhật" }).click();

  step = "wait-for-real-reconnect";
  const [connectionEvidence] = await Promise.all([
    observeDisconnectAndRecovery(),
    page.getByText(`Đã cài xong bản ${currentVersion}.`, { exact: false }).first().waitFor({
      state: "visible",
      timeout: 300_000,
    }),
  ]);
  await getJson("/health", 120_000);

  step = "verify-installed-state";
  const [meta, progress, targets] = await Promise.all([
    getJson("/api/v1/meta"),
    getJson("/api/v1/admin/update/progress"),
    getJson("/api/v1/targets?account=UPDATER_SMOKE&month=2099-11"),
  ]);
  if (meta.app_version !== currentVersion) throw new Error("Runtime metadata still reports the previous version.");
  if (!meta.accounts.includes("UPDATER_SMOKE")) throw new Error("Marker account is missing after updater reconnect.");
  if (progress.phase !== "installed" || progress.current_version !== currentVersion || progress.error) {
    throw new Error("Updater progress did not reach a clean installed state.");
  }
  if (!targets.items.some((item) => item.account === "UPDATER_SMOKE" && Number(item.daily_target_commission) === 246813579)) {
    throw new Error("Marker target is missing after updater reconnect.");
  }
  if (await page.locator(".update-message[data-tone='danger']").count()) {
    throw new Error("Updater UI exposed a public error after reconnect.");
  }

  await page.screenshot({ path: join(evidenceDir, "updater-ui-success.png"), fullPage: true });
  await writeFile(join(evidenceDir, "summary.json"), JSON.stringify({
    schema: 1,
    status: "passed",
    previous_version: previousVersion,
    current_version: currentVersion,
    phase: "installed",
    disconnect_observed: true,
    reconnect: true,
    ...connectionEvidence,
    marker_preserved: true,
  }, null, 2));
} catch (reason) {
  await page.screenshot({ path: join(evidenceDir, "updater-ui-failure.png"), fullPage: true }).catch(() => undefined);
  await writeFile(join(evidenceDir, "summary.json"), JSON.stringify({
    schema: 1,
    status: "failed",
    previous_version: previousVersion,
    current_version: currentVersion,
    step,
    error: sanitizedError(reason),
  }, null, 2));
  throw reason;
} finally {
  await browser.close();
}
