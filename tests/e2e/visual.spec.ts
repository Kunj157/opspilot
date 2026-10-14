import { expect, type Page, test } from "@playwright/test";

import { NOW, RESPONSES } from "./fixtures/visual-data";

/**
 * Visual regression snapshots of the main pages. Data comes from fixtures,
 * the clock and time zone are fixed, motion is reduced (numbers land on their
 * final values, trails and loops stop), CSS animations are disabled, the
 * topology uses its deterministic 2D map, and timestamps are masked.
 */
test.use({ timezoneId: "UTC", locale: "en-US", reducedMotion: "reduce" });

const SNAPSHOT = { fullPage: true, animations: "disabled", maxDiffPixelRatio: 0.01 } as const;

async function stage(page: Page) {
  await page.clock.setFixedTime(NOW);
  await page.addInitScript(() => {
    // A live stream that connects and stays quiet.
    class QuietEventSource {
      static CLOSED = 2;
      readyState = 1;
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor() {
        setTimeout(() => this.onopen?.(), 0);
      }
      addEventListener() {}
      removeEventListener() {}
      close() {}
    }
    Object.defineProperty(window, "EventSource", { value: QuietEventSource });
    // The 3D view is GPU and timing dependent; the 2D map is pixel-stable.
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...rest: unknown[]) {
      return type.startsWith("webgl") ? null : original.call(this, type as "2d", ...(rest as []));
    } as typeof original;
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = RESPONSES[path];
    await route.fulfill({ status: body ? 200 : 404, json: body ?? { detail: "Not found" } });
  });
}

// Backdrop noise and dithered gradients bloat the PNGs and add nothing to a layout check.
const STYLE = ":root { --noise: none; --surface-sheen: none; } .depth-backdrop, .login-horizon { background: none !important; }";

async function shoot(page: Page, name: string) {
  await page.addStyleTag({ content: STYLE });
  await expect(page).toHaveScreenshot(name, { ...SNAPSHOT, mask: [page.locator("time")] });
}

test.describe("visual snapshots", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await stage(page);
  });

  test("command center", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("list", { name: "Recent incidents" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Service map" })).toBeVisible();
    await shoot(page, "command-center.png");
  });

  test("incidents", async ({ page }) => {
    await page.goto("/incidents");
    await expect(page.getByRole("table", { name: "Incidents" })).toBeVisible();
    await shoot(page, "incidents.png");
  });

  test("services", async ({ page }) => {
    await page.goto("/services");
    await expect(page.getByRole("list", { name: "Services" }).getByRole("listitem")).toHaveCount(6);
    await shoot(page, "services.png");
  });

  test("runbooks", async ({ page }) => {
    await page.goto("/runbooks");
    await expect(page.getByRole("list", { name: "Runbooks" })).toBeVisible();
    await shoot(page, "runbooks.png");
  });

  test("ml detector", async ({ page }) => {
    await page.goto("/models");
    await expect(page.getByRole("table", { name: "Shadow predictions by service" })).toBeVisible();
    await shoot(page, "models.png");
  });

  test("audit log", async ({ page }) => {
    await page.goto("/audit-logs");
    await expect(page.getByRole("list", { name: "Audit records" })).toBeVisible();
    await shoot(page, "audit-log.png");
  });

  test("evaluations", async ({ page }) => {
    await page.goto("/evaluations");
    await expect(page.getByRole("list", { name: "Investigation outcomes" })).toBeVisible();
    await shoot(page, "evaluations.png");
  });

  test("system status", async ({ page }) => {
    await page.goto("/status");
    await expect(page.getByText("Operational").first()).toBeVisible();
    await shoot(page, "system-status.png");
  });

  test("command palette", async ({ page }) => {
    await page.goto("/incidents");
    await expect(page.getByRole("table", { name: "Incidents" })).toBeVisible();
    const palette = page.getByRole("dialog", { name: "Command palette" });
    await expect(async () => {
      if (!(await palette.isVisible())) await page.keyboard.press("ControlOrMeta+k");
      await expect(palette).toBeVisible({ timeout: 1_000 });
    }).toPass();
    await palette.getByRole("combobox").fill("check");
    await expect(palette.getByRole("option").first()).toBeVisible();
    await page.addStyleTag({ content: STYLE });
    await expect(page).toHaveScreenshot("command-palette.png", { animations: "disabled", maxDiffPixelRatio: 0.01 });
  });
});

test.describe("visual snapshots on a phone", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await stage(page);
  });

  test("command center", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("list", { name: "Recent incidents" })).toBeVisible();
    await shoot(page, "command-center-phone.png");
  });
});

test.describe("signed out", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("login", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.addStyleTag({ content: STYLE });
    await expect(page).toHaveScreenshot("login.png", SNAPSHOT);
  });
});
