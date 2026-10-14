import { expect, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

async function createIncident(page: import("@playwright/test").Page, baseURL: string, title: string) {
  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL },
    data: { title, severity: "high" },
  });
  expect(created.status()).toBe(201);
  return (await created.json()) as { id: string };
}

test("an agent investigation can be queued from the incident page", async ({ page, baseURL }) => {
  const title = `Agent run ${Date.now()}`;
  const incident = await createIncident(page, baseURL!, title);
  await page.goto(`/incidents/${incident.id}`);

  const panel = page.getByRole("region", { name: "Agent investigation" });
  await expect(panel).toContainText("No agent has investigated this incident yet.");
  await panel.getByRole("button", { name: "Run agent investigation" }).click();

  await expect(panel).toContainText("Queued");
  await expect(page.getByRole("region", { name: "Notifications" })).toContainText("Investigation queued");
  await expect(panel.getByRole("button", { name: /run agent/i })).toHaveCount(0);
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("the panel is visible but investigations cannot be started", async ({ page }) => {
    await page.goto("/incidents");
    const first = page.getByRole("table").getByRole("link").first();
    await first.click();

    const panel = page.getByRole("region", { name: "Agent investigation" });
    await expect(panel).toBeVisible();
    await expect(panel.getByRole("button")).toHaveCount(0);
  });
});
