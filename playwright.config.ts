import { defineConfig, devices } from "@playwright/test";

const apiPort = 18100;
const webPort = 15173;
const adminPort = 15174;

process.env.E2E_ADMIN_USERNAME ??= "synthetic_e2e_admin";
process.env.E2E_ADMIN_EMAIL ??= "synthetic-e2e-admin@example.com";
process.env.E2E_ADMIN_PASSWORD ??= "Synthetic-E2E-Admin-2026";
process.env.E2E_WEB_PASSWORD ??= "Synthetic-E2E-Web-2026";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: ".local/playwright/results",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: [
    ["list"],
    ["html", { outputFolder: ".local/playwright/report", open: "never" }],
  ],
  expect: {
    timeout: 10_000,
  },
  use: {
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "web-chromium",
      testMatch: /web-.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: `http://127.0.0.1:${webPort}`,
      },
    },
    {
      name: "admin-chromium",
      testMatch: /admin-.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: `http://127.0.0.1:${adminPort}`,
      },
    },
  ],
  webServer: [
    {
      command: "node scripts/e2e/start-api.mjs",
      url: `http://127.0.0.1:${apiPort}/api/v1/health/ready`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        E2E_API_PORT: String(apiPort),
        E2E_WEB_ORIGIN: `http://127.0.0.1:${webPort}`,
        E2E_ADMIN_ORIGIN: `http://127.0.0.1:${adminPort}`,
      },
    },
    {
      command: `pnpm --dir apps/web exec vite --host 127.0.0.1 --port ${webPort} --strictPort`,
      url: `http://127.0.0.1:${webPort}`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        VITE_API_BASE_URL: `http://127.0.0.1:${apiPort}/api/v1`,
      },
    },
    {
      command: `pnpm --dir apps/admin exec vite --host 127.0.0.1 --port ${adminPort} --strictPort`,
      url: `http://127.0.0.1:${adminPort}/login`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        VITE_API_BASE_URL: `http://127.0.0.1:${apiPort}/api/v1`,
      },
    },
  ],
});
