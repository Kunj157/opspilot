import { expect, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

test("an incident is created, investigated, and resolved entirely through the UI", async ({ page }) => {
  const title = `Lifecycle ${Date.now()}`;
  await page.goto("/incidents");
  await page.getByRole("button", { name: "New incident" }).click();
  const dialog = page.getByRole("dialog", { name: "New incident" });
  await dialog.getByLabel("Title").fill(title);
  await dialog.getByLabel("Severity").selectOption("critical");
  await dialog.getByRole("button", { name: "Create incident" }).click();

  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible();
  const timeline = page.getByRole("list", { name: "Timeline" });
  await expect(timeline).toContainText("Incident detected");

  const actions = page.getByRole("group", { name: "Incident actions" });
  await actions.getByRole("button", { name: "Acknowledge" }).click();
  await expect(timeline).toContainText("Acknowledged");
  await actions.getByRole("button", { name: "Start investigation" }).click();
  await expect(timeline).toContainText("Detected → Investigating");
  await actions.getByRole("button", { name: "Move to monitoring" }).click();
  await expect(timeline).toContainText("Investigating → Monitoring");
  await actions.getByRole("button", { name: "Resolve" }).click();

  await expect(timeline).toContainText("Monitoring → Resolved");
  await expect(page.getByText("Resolved", { exact: true }).first()).toBeVisible();
  await expect(actions).toHaveCount(0);
  await expect(page.getByText("Duration")).toBeVisible();
});

async function createIncident(page: import("@playwright/test").Page, baseURL: string, title: string) {
  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL },
    data: { title, severity: "high" },
  });
  expect(created.status()).toBe(201);
  return (await created.json()) as { id: string; version: number; title: string };
}

test("a change made elsewhere arrives live", async ({ page, baseURL }) => {
  const incident = await createIncident(page, baseURL!, `Elsewhere ${Date.now()}`);
  await page.goto(`/incidents/${incident.id}`);
  await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible();

  const other = await page.request.post(`/api/v1/incidents/${incident.id}/investigate`, {
    headers: { Origin: baseURL! },
    data: { version: incident.version },
  });
  expect(other.status()).toBe(200);

  await expect(page.getByRole("list", { name: "Timeline" })).toContainText("Detected → Investigating");
  await expect(page.getByRole("button", { name: "Start investigation" })).toHaveCount(0);
});

test("an action on a stale incident explains the conflict and refreshes", async ({ page, baseURL }) => {
  const incident = await createIncident(page, baseURL!, `Stale ${Date.now()}`);
  // No live updates, so the page keeps the version it loaded.
  await page.route("**/stream", (route) => route.abort());
  await page.goto(`/incidents/${incident.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(incident.title);

  const edit = await page.request.patch(`/api/v1/incidents/${incident.id}`, {
    headers: { Origin: baseURL! },
    data: { version: incident.version, title: `${incident.title} (edited)` },
  });
  expect(edit.status()).toBe(200);
  await page.getByRole("button", { name: "Acknowledge" }).click();

  await expect(page.getByRole("main").getByRole("alert")).toContainText(/someone else changed this incident/i);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("(edited)");
});

test("an unknown incident shows a friendly not-found state", async ({ page }) => {
  await page.goto("/incidents/00000000-0000-4000-8000-000000000000");

  await expect(page.getByText("Incident not found")).toBeVisible();
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("sees the incident and timeline but no actions", async ({ page }) => {
    await page.goto("/incidents?status=all");
    const first = page.getByRole("table").getByRole("link").first();
    await first.click();

    await expect(page.getByRole("list", { name: "Timeline" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Incident actions" })).toHaveCount(0);
  });
});
