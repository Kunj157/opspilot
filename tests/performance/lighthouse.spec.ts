import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { chromium, expect, test } from "@playwright/test";
import lighthouse from "lighthouse";
import desktopConfig from "lighthouse/core/config/desktop-config.js";

// UI acceptance budgets: performance ≥ 85 and accessibility ≥ 90 on primary pages.
const BUDGET = { performance: 85, accessibility: 90 };
const PAGES = ["/login", "/", "/incidents", "/services"];
const PORT = 9333;
const OUT = "test-results/lighthouse";

type Result = { path: string; performance: number; accessibility: number; scriptKiB: number };

test("primary pages meet the lighthouse budgets", async ({ baseURL }) => {
  const state = JSON.parse(readFileSync("playwright/.auth/commander.json", "utf8")) as {
    cookies: Parameters<import("@playwright/test").BrowserContext["addCookies"]>[0];
  };
  const context = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "lighthouse-")), {
    args: [`--remote-debugging-port=${PORT}`],
  });
  const results: Result[] = [];
  try {
    for (const path of PAGES) {
      // The login page is measured signed out, everything else signed in.
      await context.clearCookies();
      if (path !== "/login") await context.addCookies(state.cookies);
      const run = await lighthouse(
        `${baseURL}${path}`,
        { port: PORT, output: "json", logLevel: "error", onlyCategories: ["performance", "accessibility"] },
        desktopConfig,
      );
      const lhr = run!.lhr;
      const scripts = (lhr.audits["resource-summary"].details as { items: { resourceType: string; transferSize: number }[] }).items;
      results.push({
        path,
        performance: Math.round(lhr.categories.performance.score! * 100),
        accessibility: Math.round(lhr.categories.accessibility.score! * 100),
        scriptKiB: Math.round((scripts.find((i) => i.resourceType === "script")?.transferSize ?? 0) / 1024),
      });
    }
  } finally {
    await context.close();
  }

  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, "summary.json"), `${JSON.stringify(results, null, 2)}\n`);
  console.table(results);
  for (const r of results) {
    expect.soft(r.performance, `${r.path} performance`).toBeGreaterThanOrEqual(BUDGET.performance);
    expect.soft(r.accessibility, `${r.path} accessibility`).toBeGreaterThanOrEqual(BUDGET.accessibility);
  }
});
