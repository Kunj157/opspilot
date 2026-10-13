import { expect, test, type Page } from "@playwright/test";

/** Collects console errors and failed same-origin requests for the whole test. */
function watchForErrors(page: Page) {
  const problems: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(`console: ${msg.text()}`);
  });
  page.on("pageerror", (err) => problems.push(`pageerror: ${err.message}`));
  return problems;
}

function component(page: Page, name: string) {
  return page.getByRole("list", { name: "Components" }).getByRole("listitem", { name });
}

test("shows all systems operational against the real API", async ({ page }) => {
  const problems = watchForErrors(page);

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "System status" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("All systems operational");
  for (const name of ["API", "Configuration", "Database", "Redis"]) {
    await expect(component(page, name)).toContainText("Operational");
  }
  await expect(page.getByText(/^Checked /)).toBeVisible();
  expect(problems).toEqual([]);
});

test("names the failing dependency when the API reports not ready", async ({ page }) => {
  await page.route("**/api/v1/ready", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        status: "not_ready",
        checks: {
          config: { status: "ok", detail: null },
          database: { status: "ok", detail: null },
          redis: { status: "fail", detail: "unavailable" },
        },
      }),
    }),
  );

  await page.goto("/");

  await expect(page.getByRole("status")).toHaveText("Degraded");
  await expect(component(page, "Redis")).toContainText("Unavailable");
  await expect(component(page, "Database")).toContainText("Operational");
});

test("shows the API as unreachable when the request fails", async ({ page }) => {
  await page.route("**/api/v1/ready", (route) => route.abort("connectionrefused"));

  await page.goto("/");

  await expect(page.getByRole("status")).toHaveText("API unreachable");
  await expect(component(page, "API")).toContainText("Unreachable");
  await expect(component(page, "Redis")).toContainText("Unknown");
});

test("recovers on the next poll once the API is back", async ({ page }) => {
  await page.clock.install();
  let fail = true;
  await page.route("**/api/v1/ready", (route) =>
    fail ? route.abort("connectionrefused") : route.continue(),
  );

  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("API unreachable");

  fail = false;
  await page.clock.runFor(10_000);

  await expect(page.getByRole("status")).toHaveText("All systems operational");
});

test("has no horizontal scroll at every breakpoint", async ({
  page,
}, testInfo) => {
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("status")).toHaveText("All systems operational");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);

    await testInfo.attach(`system-status-${width}`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  }
});

test("reduced motion disables the fetch pulse animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  // Hold the request open so the fetch indicator is guaranteed to be pulsing.
  await page.route("**/api/v1/ready", () => {});

  await page.goto("/");
  const indicator = page.getByTestId("fetch-indicator");
  await expect(indicator).toHaveClass(/animate-pulse/);

  const seconds = await indicator.evaluate((el) => parseFloat(getComputedStyle(el).animationDuration));
  expect(seconds).toBeLessThan(0.001);
});

test("animates the fetch pulse when motion is allowed", async ({ page }) => {
  await page.route("**/api/v1/ready", () => {});

  await page.goto("/");
  const indicator = page.getByTestId("fetch-indicator");
  await expect(indicator).toHaveClass(/animate-pulse/);

  const seconds = await indicator.evaluate((el) => parseFloat(getComputedStyle(el).animationDuration));
  expect(seconds).toBeGreaterThan(0.5);
});
