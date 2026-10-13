import { defineConfig } from "@playwright/test";

import base from "./playwright.config";

/** Lighthouse budgets against the production build, signed in as the commander. */
export default defineConfig({
  ...base,
  testDir: "tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  projects: [
    { name: "setup", testMatch: /e2e\/auth\.setup\.ts/ },
    { name: "lighthouse", testMatch: /performance\/lighthouse\.spec\.ts/, dependencies: ["setup"] },
  ],
});
