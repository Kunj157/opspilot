import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.API_PORT ?? "8000";
const webPort = process.env.WEB_PORT ?? "3000";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: "tests/e2e",
  outputDir: "test-results",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: webUrl,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run --directory apps/api opspilot-api",
      url: `${apiUrl}/api/v1/health`,
      env: { API_PORT: apiPort, APP_ENV: "test" },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `pnpm --filter @opspilot/web build && pnpm --filter @opspilot/web start --port ${webPort}`,
      url: webUrl,
      env: { API_URL: apiUrl },
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
