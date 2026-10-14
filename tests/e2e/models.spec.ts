import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

test.beforeAll(() => {
  execFileSync("uv", ["run", "--directory", "apps/api", "python", "../../tests/e2e/fixtures/seed_model.py"]);
});

test("the ML detector page compares the model with the baseline", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").first().getByRole("link", { name: "ML detector" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "ML detector" })).toBeVisible();
  const comparison = page.getByRole("table", { name: "Detector comparison" });
  await expect(comparison.getByRole("row", { name: /^F1/ })).toContainText("0.87 (better)");
  await expect(page.getByRole("status").filter({ hasText: "promotion rule" })).toContainText("Meets the promotion rule");
  await expect(page.getByRole("region", { name: "Shadow mode" })).toBeVisible();
  // Incident commanders see versions but cannot promote; that is for administrators.
  await expect(page.getByRole("region", { name: "Model versions" }).getByRole("button")).toHaveCount(0);
});
