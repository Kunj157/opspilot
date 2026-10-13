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

test("the command center counts a newly reported incident", async ({ page, baseURL }) => {
  await page.goto("/");
  const active = page.getByRole("group", { name: "Active incidents" });
  await expect(active).toBeVisible();
  const before = Number(await active.locator("p").nth(1).textContent());

  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL! },
    data: { title: `Shell check ${Date.now()}`, severity: "critical" },
  });
  expect(created.status()).toBe(201);
  await page.reload();

  await expect(active.locator("p").nth(1)).toHaveText(String(before + 1));
  await expect(page.getByRole("list", { name: "Recent incidents" })).toContainText(
    (await created.json()).title,
  );
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
    for (const path of ["/", "/incidents", "/services", "/status", "/audit-logs"]) {
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
