import { defineConfig } from "@playwright/test";

// Records the product walkthrough against a running stack (make dev + the
// kind demo + the worker + the local LLM). Not part of the test suite:
//   make demo-record
const webPort = process.env.WEB_PORT ?? "3000";

export default defineConfig({
  testDir: "tests/walkthrough",
  outputDir: "test-results/walkthrough",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 15 * 60_000,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${webPort}`,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: "dark",
    launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] },
  },
});
