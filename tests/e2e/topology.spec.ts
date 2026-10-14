import { expect, type APIRequestContext, type Page, test } from "@playwright/test";

/** Two services where `checkout` calls `payment`, with unique names per run. */
async function seed(request: APIRequestContext, origin: string) {
  // Parallel tests seed at the same moment, so the suffix must be random.
  const run = `${Date.now()}${Math.floor(Math.random() * 1e6)}`;
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

/** Switches to the 2D map, which is where keyboard and screen-reader users work. */
async function show2D(page: Page) {
  const toggle = page.getByRole("group", { name: "Topology view" });
  await expect(toggle.or(page.getByText("3D view unavailable"))).toBeVisible();
  if (await toggle.isVisible()) await toggle.getByRole("button", { name: "2D" }).click();
}

test("selecting a service on the map shows its dependencies", async ({ page, baseURL }) => {
  const { checkout, payment } = await seed(page.request, baseURL!);
  await page.goto("/");
  await show2D(page);

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
  await show2D(page);
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

test.describe("3D view", () => {
  test("pauses while scrolled out of view", async ({ page, baseURL }) => {
    await seed(page.request, baseURL!);
    await page.setViewportSize({ width: 1280, height: 600 });
    await page.goto("/");
    const view = page.getByTestId("topology-3d");
    await view.scrollIntoViewIfNeeded();
    await expect(view).toHaveAttribute("data-frameloop", "always");

    await page.evaluate(() => window.scrollTo(0, 0));

    await expect(view).toHaveAttribute("data-frameloop", "never");
  });

  test("is the default where WebGL works and keeps the 2D map one click away", async ({ page, baseURL }) => {
    await seed(page.request, baseURL!);
    await page.goto("/");

    const view = page.getByTestId("topology-3d");
    await view.scrollIntoViewIfNeeded();
    await expect(view.locator("canvas")).toBeVisible();
    await expect(view).toHaveAttribute("data-frameloop", "always");
    await page.getByRole("group", { name: "Topology view" }).getByRole("button", { name: "2D" }).click();
    await expect(page.getByRole("group", { name: "Service map" })).toBeVisible();
    await expect(view).toHaveCount(0);
  });

  test("falls back to the 2D map when WebGL is unavailable", async ({ page, baseURL }) => {
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...rest: unknown[]) {
        return type.startsWith("webgl") ? null : original.call(this, type as "2d", ...(rest as []));
      } as typeof original;
    });
    await seed(page.request, baseURL!);
    await page.goto("/");

    await expect(page.getByText("3D view unavailable")).toBeVisible();
    await expect(page.getByRole("group", { name: "Service map" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Topology view" })).toHaveCount(0);
    await expect(page.getByTestId("topology-3d")).toHaveCount(0);
  });

  test("falls back to the 2D map when the WebGL context is lost", async ({ page, baseURL }) => {
    await seed(page.request, baseURL!);
    await page.goto("/");
    const canvas = page.getByTestId("topology-3d").locator("canvas");
    await expect(canvas).toBeVisible();

    await canvas.evaluate((node: HTMLCanvasElement) => {
      const gl = node.getContext("webgl2") ?? node.getContext("webgl");
      gl?.getExtension("WEBGL_lose_context")?.loseContext();
    });

    await expect(page.getByRole("group", { name: "Service map" })).toBeVisible();
    await expect(page.getByText("3D view unavailable")).toBeVisible();
  });

  test("focusing a service flies the camera to it and reset returns to the overview", async ({ page, baseURL }) => {
    const { checkout } = await seed(page.request, baseURL!);
    await page.goto(`/?focus=${checkout.id}`);

    const view = page.getByTestId("topology-3d");
    await expect(view).toHaveAttribute("data-camera-target", checkout.id);
    const details = page.getByRole("region", { name: "Selected service" });
    await expect(details.getByRole("heading", { name: checkout.name })).toBeVisible();

    await page.getByRole("button", { name: "Reset view" }).click();
    await expect(view).toHaveAttribute("data-camera-target", "overview");
    await expect(page.getByRole("button", { name: "Reset view" })).toHaveCount(0);
  });

  test("selecting on the 2D map carries over to the 3D camera", async ({ page, baseURL }) => {
    const { payment } = await seed(page.request, baseURL!);
    await page.goto("/");
    await show2D(page);
    await page.getByRole("group", { name: "Service map" }).getByRole("button", { name: new RegExp(`^${payment.name}`) }).click();

    await page.getByRole("group", { name: "Topology view" }).getByRole("button", { name: "3D" }).click();

    await expect(page.getByTestId("topology-3d")).toHaveAttribute("data-camera-target", payment.id);
  });

  test("jumps the camera without flying under reduced motion", async ({ page, baseURL }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    const { checkout } = await seed(page.request, baseURL!);
    await page.goto(`/?focus=${checkout.id}`);

    await expect(page.getByTestId("topology-3d")).toHaveAttribute("data-camera-target", checkout.id);
  });

  test("renders on demand only when the user prefers reduced motion", async ({ page, baseURL }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await seed(page.request, baseURL!);
    await page.goto("/");

    const view = page.getByTestId("topology-3d");
    await view.scrollIntoViewIfNeeded();
    await expect(view).toHaveAttribute("data-frameloop", "demand");
  });

  test("stops rendering while the tab is hidden", async ({ page, baseURL }) => {
    await seed(page.request, baseURL!);
    await page.goto("/");
    const view = page.getByTestId("topology-3d");
    await view.scrollIntoViewIfNeeded();
    await expect(view).toHaveAttribute("data-frameloop", "always");

    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
      document.dispatchEvent(new Event("visibilitychange"));
    });

    await expect(view).toHaveAttribute("data-frameloop", "never");
  });
});
