import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.API_PORT ?? "8000";
const webPort = process.env.WEB_PORT ?? "3000";
const keycloakPort = process.env.KEYCLOAK_PORT ?? "8080";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://localhost:${webPort}`;
const issuer = process.env.JWT_ISSUER ?? `http://localhost:${keycloakPort}/realms/opspilot`;

export const AUTH_DIR = "playwright/.auth";

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
  projects: [
    { name: "setup", testMatch: /.*\.setup\.ts/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: `${AUTH_DIR}/commander.json` },
      dependencies: ["setup"],
    },
  ],
  webServer: [
    {
      command: "uv run --directory apps/api opspilot-api",
      url: `${apiUrl}/api/v1/health`,
      // Deterministic embeddings: the browser tests never download a model.
      env: { API_PORT: apiPort, APP_ENV: "test", JWT_ISSUER: issuer, JWT_AUDIENCE: "opspilot-api", EMBEDDING_MODEL: "hashing" },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `pnpm --filter @opspilot/web build && pnpm --filter @opspilot/web start --port ${webPort}`,
      url: `${webUrl}/login`,
      env: {
        API_URL: apiUrl,
        OIDC_ISSUER: issuer,
        OIDC_CLIENT_ID: "opspilot-web",
        OIDC_CLIENT_SECRET: "opspilot-web-dev-only",
      },
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
