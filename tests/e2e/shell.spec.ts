import { expect, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

test("the sidebar navigates between sections", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });

  await expect(nav.getByRole("link", { name: "Command center" })).toHaveAttribute("aria-current", "page");
  await nav.getByRole("link", { name: "System status" }).click();

  await expect(page).toHaveURL(/\/status$/);
  await expect(page.getByRole("heading", { name: "System status" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "System status" })).toHaveAttribute("aria-current", "page");
});

test("the command center matches the active incidents the API reports", async ({ page, baseURL }) => {
  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL! },
    data: { title: `Shell check ${Date.now()}`, severity: "critical" },
  });
  expect(created.status()).toBe(201);
  const active = ["DETECTED", "INVESTIGATING", "AWAITING_APPROVAL", "REMEDIATING", "VERIFYING", "MONITORING", "REJECTED"];
  const query = `${active.map((s) => `status=${s}`).join("&")}&limit=200`;

  // Other specs create and resolve incidents in parallel, so compare against
  // the API at the same moment and retry until both agree.
  await expect(async () => {
    await page.goto("/");
    const recent = page.getByRole("list", { name: "Recent incidents" });
    await expect(recent).toBeVisible();
    const items = (await (await page.request.get(`/api/v1/incidents?${query}`)).json()).items as { title: string }[];
    await expect(page.getByRole("group", { name: "Active incidents" }).locator("p").nth(1)).toHaveText(
      String(items.length),
      { timeout: 2_000 },
    );
    await expect(recent.getByRole("listitem")).toHaveText(
      items.slice(0, 5).map((i) => new RegExp(i.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))),
      { timeout: 2_000 },
    );
  }).toPass({ timeout: 30_000 });
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("navigation lives in a drawer that keyboard users can close", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();

    await page.getByRole("button", { name: "Open navigation" }).click();
    const drawer = page.getByRole("dialog", { name: "Navigation" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByTestId("user-name")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();

    await page.getByRole("button", { name: "Open navigation" }).click();
    await drawer.getByRole("link", { name: "System status" }).click();
    await expect(page).toHaveURL(/\/status$/);
    await expect(drawer).toBeHidden();
  });
});

test("no page scrolls sideways at any breakpoint", async ({ page }) => {
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/", "/incidents", "/services", "/runbooks", "/evaluations", "/status", "/audit-logs"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `${path} at ${width}px`).toBeLessThanOrEqual(0);
    }
  }
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("sees no audit log in the navigation", async ({ page }) => {
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Main" });

    await expect(nav.getByRole("link", { name: "Command center" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Audit log" })).toHaveCount(0);
  });
});
