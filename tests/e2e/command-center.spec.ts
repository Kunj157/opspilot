import { expect, test } from "@playwright/test";

test("a new incident appears in the live alert stream without reloading", async ({ page, baseURL }) => {
  await page.goto("/");
  const alerts = page.getByRole("region", { name: "Live alerts" });
  await expect(alerts.getByRole("status")).toHaveText("Live");

  const title = `Stream check ${Date.now()}`;
  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL! },
    data: { title, severity: "high" },
  });
  expect(created.status()).toBe(201);

  const item = alerts.getByRole("listitem").filter({ hasText: title });
  await expect(item).toContainText("Incident detected");
  await expect(item.getByRole("link", { name: title })).toHaveAttribute("href", `/incidents/${(await created.json()).id}`);
});

test("response-time metrics and the severity chart are shown", async ({ page }) => {
  await page.goto("/");

  for (const label of ["Mean time to acknowledge", "Mean time to resolve"]) {
    await expect(page.getByRole("group", { name: label }).locator("p").nth(1)).toHaveText(/^(—|<1m|\d+[dhm]( \d+[hm])?)$/);
  }
  const chart = page.getByRole("region", { name: /Incidents by severity/ });
  await expect(chart.getByRole("img", { name: /incidents started per day/i })).toBeVisible();
  await chart.getByRole("button", { name: "Show table" }).click();
  await expect(chart.getByRole("table").getByRole("row")).toHaveCount(15);
});
