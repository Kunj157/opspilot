import { expect, type Page, test } from "@playwright/test";

/** Clicks the top bar search until the palette opens (the button works once the page has hydrated). */
async function openWithClick(page: Page) {
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(async () => {
    if (!(await palette.isVisible())) await page.getByRole("button", { name: "Search or jump to…" }).click();
    await expect(palette).toBeVisible({ timeout: 1_000 });
  }).toPass();
  return palette;
}

/** Presses ⌘K / Ctrl K until the palette is open: the shortcut listens only once the page has hydrated. */
async function openWithShortcut(page: Page) {
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(async () => {
    if (!(await palette.isVisible())) await page.keyboard.press("ControlOrMeta+k");
    await expect(palette).toBeVisible({ timeout: 1_000 });
  }).toPass();
  return palette;
}

test("the keyboard shortcut opens the palette and jumps to a section", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  const palette = await openWithShortcut(page);
  const search = palette.getByRole("combobox", { name: "Search commands" });
  await expect(search).toBeFocused();
  await search.fill("system status");
  await expect(palette.getByRole("option").first()).toHaveText("System status");
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/status$/);
  await expect(palette).toBeHidden();
});

test("an incident can be found by title and opened", async ({ page, baseURL }) => {
  const title = `Palette check ${Date.now()}`;
  const created = await page.request.post("/api/v1/incidents", {
    headers: { Origin: baseURL! },
    data: { title, severity: "high" },
  });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };

  await page.goto("/services");
  const palette = await openWithClick(page);
  await palette.getByRole("combobox").fill(title);
  await palette.getByRole("option", { name: title }).click();

  await expect(page).toHaveURL(new RegExp(`/incidents/${id}$`));
});

test("the new incident action opens the form", async ({ page }) => {
  await page.goto("/");
  const palette = await openWithShortcut(page);
  await palette.getByRole("combobox").fill("new incident");
  await expect(palette.getByRole("option").first()).toHaveText("New incident");
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/incidents\?new=1$/);
  await expect(page.getByRole("dialog", { name: "New incident" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/\/incidents$/);
});

test("escape closes the palette and returns focus to the trigger", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Search or jump to…" });
  await openWithClick(page);

  await page.keyboard.press("Escape");

  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeHidden();
  await expect(trigger).toBeFocused();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the search icon opens the palette", async ({ page }) => {
    await page.goto("/");
    const palette = await openWithClick(page);
    await expect(palette.getByRole("combobox")).toBeFocused();
  });
});
