import { expect, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

test("creates a service, opens it, and edits it", async ({ page }) => {
  const name = `Checkout ${Date.now()}`;
  await page.goto("/services");

  await page.getByRole("button", { name: "New service" }).click();
  const dialog = page.getByRole("dialog", { name: "New service" });
  await dialog.getByLabel("Name", { exact: true }).fill(name);
  await expect(dialog.getByLabel("Slug")).toHaveValue(/^checkout-\d+$/);
  await dialog.getByLabel("Owner team").fill("payments");
  await dialog.getByLabel("Namespace").fill("demo");
  await dialog.getByRole("button", { name: "Create service" }).click();

  await expect(dialog).toBeHidden();
  const card = page.getByRole("list", { name: "Services" }).getByRole("link", { name: new RegExp(name) });
  await expect(card).toContainText("Unknown");
  await card.click();

  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.getByText("No active incidents for this service.")).toBeVisible();
  await page.getByRole("button", { name: "Edit service" }).click();
  const edit = page.getByRole("dialog", { name: "Edit service" });
  await edit.getByLabel("Owner team").fill("checkout-team");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(edit).toBeHidden();
  await expect(page.getByText("checkout-team", { exact: true })).toBeVisible();
});

test("shows validation problems next to the field", async ({ page }) => {
  await page.goto("/services");
  await page.getByRole("button", { name: "New service" }).click();
  const dialog = page.getByRole("dialog", { name: "New service" });

  await dialog.getByLabel("Name", { exact: true }).fill(`Bad ${Date.now()}`);
  await dialog.getByLabel("Namespace").fill("Not_Valid");
  await dialog.getByRole("button", { name: "Create service" }).click();

  await expect(dialog.getByLabel("Namespace")).toHaveAttribute("aria-invalid", "true");
  await expect(dialog).toBeVisible();
});

test("an unknown service shows a friendly not-found state", async ({ page }) => {
  await page.goto("/services/00000000-0000-4000-8000-000000000000");

  await expect(page.getByText("Service not found")).toBeVisible();
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("can browse but not create services", async ({ page }) => {
    await page.goto("/services");

    await expect(page.getByRole("heading", { name: "Services" })).toBeVisible();
    await expect(page.getByRole("button", { name: "New service" })).toHaveCount(0);
  });
});
