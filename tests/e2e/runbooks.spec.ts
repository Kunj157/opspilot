import { expect, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

function runbook(title: string, symptoms: string, version = 1) {
  return `---
title: ${title}
services: [checkout]
owner: shop-team
version: ${version}
---

## Symptoms

${symptoms}

## Safe actions

- Roll back with \`kubectl -n demo rollout undo deployment/checkout\`
`;
}

test("searching by symptoms finds the runbook, and editing creates a new version", async ({ page, baseURL }) => {
  const run = `${Date.now()}${Math.floor(Math.random() * 1e6)}`;
  const title = `Checkout ledger drift ${run}`;
  const created = await page.request.post("/api/v1/runbooks", {
    headers: { Origin: baseURL! },
    data: { content: runbook(title, `Ledger totals drift ${run} after checkout releases.`) },
  });
  expect(created.status()).toBe(201);

  await page.goto("/runbooks");
  await page.getByRole("searchbox", { name: "Search runbooks" }).fill(`ledger totals drift ${run}`);
  await page.getByRole("search").getByRole("button", { name: "Search" }).click();
  const first = page.getByRole("list", { name: "Search results" }).getByRole("listitem").first();
  await expect(first).toContainText(title);
  await first.getByRole("link", { name: title }).click();

  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByText("kubectl -n demo rollout undo deployment/checkout", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Edit runbook" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit runbook" });
  const editor = dialog.getByLabel("Runbook (markdown with front matter)");
  await editor.fill(runbook(title, `Ledger totals drift ${run} after checkout releases; verify refunds.`));
  await dialog.getByRole("button", { name: "Save new version" }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByRole("region", { name: "Notifications" })).toContainText("Saved version 2");
  await expect(page.getByText("v2", { exact: true })).toBeVisible();
});

test("an invalid runbook is explained, not saved", async ({ page }) => {
  await page.goto("/runbooks");
  await page.getByRole("button", { name: "New runbook" }).click();
  const dialog = page.getByRole("dialog", { name: "New runbook" });
  await dialog.getByLabel("Runbook (markdown with front matter)").fill("# no front matter");
  await dialog.getByRole("button", { name: "Create runbook" }).click();

  await expect(dialog.getByRole("alert")).toContainText("Invalid runbook");
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("runbooks are readable but not editable", async ({ page }) => {
    await page.goto("/runbooks");
    await expect(page.getByRole("heading", { level: 1, name: "Runbooks" })).toBeVisible();
    await expect(page.getByRole("button", { name: "New runbook" })).toHaveCount(0);
  });
});
