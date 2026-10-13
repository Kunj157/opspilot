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

  await expect(dialog).toBeHidden();
  const row = page.getByRole("row").filter({ has: page.getByText(title, { exact: true }) });
  await expect(row).toContainText("High");
  await expect(row).toContainText("Detected");
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

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("can follow incidents but not create them", async ({ page }) => {
    await page.goto("/incidents");

    await expect(page.getByRole("heading", { name: "Incidents", level: 1 })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible();
    await expect(page.getByRole("button", { name: "New incident" })).toHaveCount(0);
  });
});
