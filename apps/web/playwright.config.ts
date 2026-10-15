import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

// End-to-end runs get their own API (empty database in a temp dir) and their own web
// server on separate ports, so they never touch development data.
const API_PORT = 8100;
const WEB_PORT = 3100;
const here = dirname(fileURLToPath(import.meta.url));
const apiDir = resolve(here, "../api");
const venvPython = [join(apiDir, ".venv/Scripts/python.exe"), join(apiDir, ".venv/bin/python")].find(existsSync);
const python = process.env.PYTHON ?? venvPython ?? "python";
const dataDir = process.env.DERLE_E2E_DATA ?? join(tmpdir(), `derle-e2e-${Date.now()}`);
process.env.DERLE_E2E_DATA = dataDir; // keep one directory across config re-evaluation in workers

const apiUrl = `http://127.0.0.1:${API_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1, // one shared database; tests build on each other's state
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    locale: "tr-TR",
    timezoneId: "Europe/Istanbul",
    trace: "retain-on-failure",
    // Locally use the installed Chrome instead of downloading a browser.
    channel: process.env.CI ? undefined : "chrome",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } }, testIgnore: /mobile|capture/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec/ },
    { name: "capture", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 860 } }, testMatch: /capture\.spec/ },
  ],
  webServer: [
    {
      command: `"${python}" -m uvicorn derle.main:app --app-dir src --port ${API_PORT} --timeout-keep-alive 75`,
      cwd: apiDir,
      env: { DERLE_DATA_DIR: dataDir, DERLE_LLM_PROVIDER: "none" },
      url: `${apiUrl}/api/v1/health`,
      timeout: 60_000,
      reuseExistingServer: false,
    },
    {
      // Rewrites are fixed at build time, so the e2e build points at the e2e API.
      command: `npm run build && node scripts/start-standalone.mjs ${WEB_PORT}`,
      env: { DERLE_API_URL: apiUrl, NEXT_TELEMETRY_DISABLED: "1" },
      url: `http://127.0.0.1:${WEB_PORT}`,
      timeout: 240_000,
      reuseExistingServer: false,
    },
  ],
});
