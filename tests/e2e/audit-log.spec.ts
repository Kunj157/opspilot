import { expect, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

test("incident commanders reach the audit log from the navigation", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Audit log" }).click();

  await expect(page).toHaveURL(/\/audit-logs$/);
  await expect(page.getByRole("heading", { name: "Audit log" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Audit log" })).toHaveAttribute("aria-current", "page");
  // Real records exist: every user's first sign-in is audited.
  await expect(page.getByRole("list", { name: "Audit records" }).getByRole("listitem").first()).toBeVisible();
});

test("filters by action against the real api", async ({ page }) => {
  await page.goto("/audit-logs");

  await page.getByLabel("Action").fill("user.provisioned");
  await page.getByRole("button", { name: "Apply filters" }).click();

  const rows = page.getByRole("list", { name: "Audit records" }).getByRole("listitem");
  await expect(rows.first()).toContainText("user.provisioned");
  for (const row of await rows.all()) await expect(row).toContainText("user.provisioned");
});

test("loads further pages on request", async ({ page }) => {
  const entry = (n: number) => ({
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    actor_type: "user",
    actor_id: `user-${n}`,
    action: "http.post",
    resource_type: "http_request",
    resource_id: `/api/v1/things/${n}`,
    ip_address: null,
    request_id: `req-${n}`,
    metadata: {},
    created_at: new Date(Date.UTC(2026, 9, 13, 12, 0, n)).toISOString(),
  });
  await page.route("**/api/v1/audit-logs**", (route) => {
    const cursor = new URL(route.request().url()).searchParams.get("cursor");
    const body = cursor
      ? { items: [entry(1)], next_cursor: null }
      : { items: [entry(3), entry(2)], next_cursor: "page-2" };
    return route.fulfill({ json: body });
  });

  await page.goto("/audit-logs");
  const rows = page.getByRole("list", { name: "Audit records" }).getByRole("listitem");
  await expect(rows).toHaveCount(2);
  await page.getByRole("button", { name: "Load more" }).click();

  await expect(rows).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Load more" })).toHaveCount(0);
});

test("fits a phone screen without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/audit-logs");
  await expect(page.getByRole("list", { name: "Audit records" })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("has no audit log entry and is refused on direct access", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Audit log" })).toHaveCount(0);

    await page.goto("/audit-logs");

    await expect(page.getByRole("alert").filter({ hasText: "don't have access" })).toBeVisible();
    await expect(page.getByRole("list", { name: "Audit records" })).toHaveCount(0);
  });
});
