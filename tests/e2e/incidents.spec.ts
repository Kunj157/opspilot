import { expect, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

test("a new incident appears in the list without a reload", async ({ page, baseURL }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto("/incidents");
  await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible();

  const title = `Live list ${Date.now()}`;
  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL! },
    data: { title, severity: "critical" },
  });
  expect(created.status()).toBe(201);

  await expect(page.getByText(title, { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("creates an incident from the dialog", async ({ page }) => {
  const title = `Dialog ${Date.now()}`;
  await page.goto("/incidents");

  await page.getByRole("button", { name: "New incident" }).click();
  const dialog = page.getByRole("dialog", { name: "New incident" });
  await dialog.getByRole("button", { name: "Create incident" }).click();
  await expect(dialog.getByLabel("Title")).toHaveAttribute("aria-invalid", "true");

  await dialog.getByLabel("Title").fill(title);
  await dialog.getByLabel("Severity").selectOption("high");
  await dialog.getByRole("button", { name: "Create incident" }).click();

  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await page.getByRole("link", { name: "← Incidents" }).click();
  const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: title }) });
  await expect(row).toContainText("High");
  await expect(row).toContainText("Detected");
});

test("a ?new=1 link opens the new incident form and closing it tidies the URL", async ({ page }) => {
  await page.goto("/incidents?new=1&severity=high");
  const dialog = page.getByRole("dialog", { name: "New incident" });
  await expect(dialog).toBeVisible();

  await dialog.getByRole("button", { name: "Close" }).click();

  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(/\/incidents\?severity=high$/);
});

test("filters are kept in the URL and survive a reload", async ({ page, baseURL }) => {
  const stamp = Date.now();
  for (const severity of ["critical", "low"]) {
    const response = await page.request.post("/api/v1/incidents", {
      headers: { Origin: baseURL! },
      data: { title: `Filter ${severity} ${stamp}`, severity },
    });
    expect(response.status()).toBe(201);
  }
  await page.goto("/incidents");
  await expect(page.getByText(`Filter low ${stamp}`, { exact: true })).toBeVisible();

  await page.getByLabel("Severity").selectOption("critical");

  await expect(page).toHaveURL(/\/incidents\?severity=critical$/);
  await expect(page.getByText(`Filter critical ${stamp}`, { exact: true })).toBeVisible();
  await expect(page.getByText(`Filter low ${stamp}`, { exact: true })).toHaveCount(0);

  await page.reload();
  await expect(page.getByLabel("Severity")).toHaveValue("critical");
  await expect(page.getByText(`Filter low ${stamp}`, { exact: true })).toHaveCount(0);

  await page.getByLabel("Status").selectOption("RESOLVED");
  await expect(page).toHaveURL(/status=RESOLVED/);
  await expect(page.getByText(`Filter critical ${stamp}`, { exact: true })).toHaveCount(0);
});

test("filters by assignee", async ({ page, baseURL }) => {
  const stamp = Date.now();
  const headers = { Origin: baseURL! };
  const me = (await (await page.request.get("/api/v1/me")).json()) as { id: string };
  const make = async (title: string) => {
    const response = await page.request.post("/api/v1/incidents", { headers, data: { title, severity: "low" } });
    expect(response.status()).toBe(201);
    return (await response.json()) as { id: string; version: number };
  };
  const mine = await make(`Assigned ${stamp}`);
  await make(`Unassigned ${stamp}`);
  const assigned = await page.request.patch(`/api/v1/incidents/${mine.id}`, {
    headers,
    data: { version: mine.version, assigned_user_id: me.id },
  });
  expect(assigned.status()).toBe(200);

  await page.goto("/incidents");
  await expect(page.getByText(`Unassigned ${stamp}`, { exact: true })).toBeVisible();
  await page.getByLabel("Assignee").selectOption("me");

  await expect(page).toHaveURL(/\/incidents\?mine=1$/);
  await expect(page.getByText(`Assigned ${stamp}`, { exact: true })).toBeVisible();
  await expect(page.getByText(`Unassigned ${stamp}`, { exact: true })).toHaveCount(0);
});

test("columns sort and the header stays visible while scrolling", async ({ page, baseURL }) => {
  // Enough rows to scroll a short window, whatever else the suite has created.
  for (const severity of ["critical", "high", "medium", "low", "low", "low", "low", "low"]) {
    const response = await page.request.post("/api/v1/incidents", {
      headers: { Origin: baseURL! },
      data: { title: `Sort ${severity} ${Date.now()}`, severity },
    });
    expect(response.status()).toBe(201);
  }
  await page.setViewportSize({ width: 1280, height: 480 });
  await page.goto("/incidents?status=all");
  const table = page.getByRole("table", { name: "Incidents" });
  const severity = table.getByRole("columnheader", { name: "Severity" });

  await severity.getByRole("button").click();
  await expect(severity).toHaveAttribute("aria-sort", "ascending");
  await expect(table.getByRole("row").nth(1)).toContainText("Critical");
  await severity.getByRole("button").click();
  await expect(severity).toHaveAttribute("aria-sort", "descending");

  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const box = await severity.boundingBox();
  // Pinned just below the 48px top bar.
  expect(box?.y).toBeGreaterThanOrEqual(47);
  expect(box?.y).toBeLessThanOrEqual(49);
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("can follow incidents but not create them", async ({ page }) => {
    await page.goto("/incidents");

    await expect(page.getByRole("heading", { name: "Incidents", level: 1 })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible();
    await expect(page.getByRole("button", { name: "New incident" })).toHaveCount(0);
  });
});
