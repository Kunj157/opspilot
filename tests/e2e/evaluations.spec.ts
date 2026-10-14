import { expect, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

test("the evaluations dashboard shows live metrics and switches range", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Evaluations" }).click();

  await expect(page).toHaveURL(/\/evaluations$/);
  await expect(page.getByRole("heading", { level: 1, name: "Evaluations" })).toBeVisible();
  for (const name of ["Agents", "Investigations", "Detection", "Remediation and response", "Token usage"]) {
    await expect(page.getByRole("region", { name })).toBeVisible();
  }
  await expect(page.getByRole("group", { name: "Detector incidents" }).locator("p").nth(1)).toHaveText(/^\d+$/);

  await page.getByRole("group", { name: "Time range" }).getByRole("button", { name: "7d" }).click();
  await expect(page).toHaveURL(/\/evaluations\?days=7$/);
  await expect(page.getByText("Last 7 days")).toBeVisible();
  await expect(page.getByRole("button", { name: "7d" })).toHaveAttribute("aria-pressed", "true");
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("can read the evaluations", async ({ page }) => {
    await page.goto("/evaluations");
    await expect(page.getByRole("region", { name: "Agents" })).toBeVisible();
  });
});
