import { defineConfig } from "@playwright/test";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const repoRoot = resolve(__dirname, "..");
const port = Number(process.env.E2E_PORT ?? 8123);
const venvPython = join(repoRoot, ".venv", "Scripts", "python.exe");
const python = process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");
// Database tạm mỗi lần chạy: kịch bản kiểm cả trạng thái rỗng sau khi hoàn tác.
const dataDir = mkdtempSync(join(tmpdir(), "tiktok-affiliate-e2e-"));

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}` },
  webServer: {
    command: `"${python}" run_api.py`,
    cwd: repoRoot,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      AUTH_MODE: "local",
      API_HOST: "127.0.0.1",
      API_PORT: String(port),
      DATABASE_URL: `sqlite:///${join(dataDir, "e2e.db").replace(/\\/g, "/")}`,
      WEB_STATIC_DIR: join(repoRoot, "web", "out"),
    },
  },
});
