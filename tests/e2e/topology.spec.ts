import { expect, type APIRequestContext, test } from "@playwright/test";

/** Two services where `checkout` calls `payment`, with unique names per run. */
async function seed(request: APIRequestContext, origin: string) {
  const run = Date.now();
  const headers = { Origin: origin };
  const make = async (name: string) => {
    const response = await request.post("/api/v1/services", {
      headers,
      data: { name: `${name} ${run}`, slug: `${name.toLowerCase()}-${run}` },
    });
    expect(response.status()).toBe(201);
    return (await response.json()) as { id: string; name: string };
  };
  const checkout = await make("Checkout");
  const payment = await make("Payment");
  const deps = await request.put(`/api/v1/services/${checkout.id}/dependencies`, {
    headers,
    data: { target_ids: [payment.id] },
  });
  expect(deps.status()).toBe(200);
  return { checkout, payment };
}

test("selecting a service on the map shows its dependencies", async ({ page, baseURL }) => {
  const { checkout, payment } = await seed(page.request, baseURL!);
  await page.goto("/");

  const map = page.getByRole("group", { name: "Service map" });
  await map.getByRole("button", { name: new RegExp(`^${checkout.name}`) }).click();

  const details = page.getByRole("region", { name: "Selected service" });
  await expect(details.getByRole("heading", { name: checkout.name })).toBeVisible();
  await expect(details.getByRole("list", { name: "Calls" })).toHaveText(payment.name);
  await details.getByRole("link", { name: `Open ${checkout.name}` }).click();
  await expect(page).toHaveURL(new RegExp(`/services/${checkout.id}$`));
});

test("the map works from the keyboard", async ({ page, baseURL }) => {
  const { checkout } = await seed(page.request, baseURL!);
  await page.goto("/");
  const map = page.getByRole("group", { name: "Service map" });
  const checkoutNode = map.getByRole("button", { name: new RegExp(`^${checkout.name}`) });
  await expect(checkoutNode).toBeVisible();

  // One tab stop for the whole map.
  await expect(map.locator('[tabindex="0"]')).toHaveCount(1);
  await checkoutNode.focus();
  await expect(checkoutNode).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(new RegExp(`/services/${checkout.id}$`));
  await expect(page.getByRole("heading", { level: 1, name: checkout.name })).toBeVisible();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the topology becomes a list", async ({ page, baseURL }) => {
    const { checkout, payment } = await seed(page.request, baseURL!);
    await page.goto("/");

    await expect(page.getByRole("group", { name: "Service map" })).toBeHidden();
    const list = page.getByRole("list", { name: "Services by dependency" });
    const item = list.getByRole("listitem").filter({ hasText: checkout.name });
    await expect(item).toContainText(`Calls ${payment.name}`);
  });
});
