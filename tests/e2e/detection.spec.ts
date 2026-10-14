import { expect, test } from "@playwright/test";

test("detector incidents are labelled and show their detection panel", async ({ page, baseURL }) => {
  const title = `High error rate ${Date.now()}`;
  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL! },
    data: { title, severity: "critical", source: "detector" },
  });
  expect(created.status()).toBe(201);
  const { id } = await created.json();

  await page.goto("/incidents");
  const row = page.getByRole("row").filter({ hasText: title });
  await expect(row).toContainText("Detected automatically");

  await row.getByRole("link", { name: title }).click();
  const panel = page.getByRole("region", { name: "Detection" });
  await expect(panel).toContainText("No detector readings recorded for this incident.");
  await expect(page).toHaveURL(new RegExp(`/incidents/${id}$`));
});

test("manual incidents have no detection panel", async ({ page, baseURL }) => {
  const title = `Manual ${Date.now()}`;
  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL! },
    data: { title, severity: "low" },
  });
  await page.goto(`/incidents/${(await created.json()).id}`);

  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByRole("region", { name: "Detection" })).toHaveCount(0);
});
