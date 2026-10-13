import { expect, test } from "@playwright/test";

import { AUTH_DIR, signIn, signInOnKeycloak } from "./support";

test.describe("signed out", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("protected pages redirect to the login page", async ({ page }) => {
    await page.goto("/");

    await expect(page).toHaveURL(/\/login\?returnTo=%2F$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("signs in through keycloak and lands on the command center", async ({ page }) => {
    await signIn(page, "commander");

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("user-name")).toHaveText("Cleo Commander");
    await expect(page.getByText("acme", { exact: true })).toBeVisible();
    await expect(page.getByRole("list", { name: "Your roles" })).toHaveText("Incident commander");
  });

  test("returns to the page that was requested before sign-in", async ({ page }) => {
    await page.goto("/?view=compact");
    await page.getByRole("link", { name: "Continue with single sign-on" }).click();
    await signInOnKeycloak(page, "viewer");

    await expect(page).toHaveURL(/\/\?view=compact$/);
  });

  test("the api proxy refuses calls without a session", async ({ page }) => {
    await page.goto("/login");

    const status = await page.evaluate(async () => (await fetch("/api/v1/me")).status);

    expect(status).toBe(401);
  });

  test("a broken sign-in callback shows an error instead of failing", async ({ page }) => {
    await page.goto("/auth/callback?code=forged&state=forged");

    await expect(page).toHaveURL(/\/login\?error=callback$/);
    await expect(
      page.getByRole("alert").filter({ hasText: "could not be completed" }),
    ).toBeVisible();
  });

  test("a forged return address cannot redirect off-site", async ({ page }) => {
    await page.goto("/login?returnTo=%2F%2Fevil.example%2F");
    await page.getByRole("link", { name: "Continue with single sign-on" }).click();
    await signInOnKeycloak(page, "admin");

    await expect(page).toHaveURL(/^http:\/\/localhost:\d+\/$/);
  });
});

test.describe("signed in", () => {
  test("tokens never reach browser javascript", async ({ page, context, baseURL }) => {
    await page.goto("/");
    await expect(page.getByTestId("user-name")).toBeVisible();

    // Only the app's own cookies; the identity provider's cookies live on its origin.
    const appCookies = await context.cookies(baseURL);
    const session = appCookies.find((c) => c.name === "opspilot_session");
    expect(session?.httpOnly).toBe(true);
    expect(session?.sameSite).toBe("Lax");
    for (const cookie of appCookies) expect(cookie.value).not.toContain("eyJ");

    const visible = await page.evaluate(() => ({
      cookie: document.cookie,
      storage: JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }),
    }));
    expect(visible.cookie).not.toContain("opspilot_session");
    expect(visible.storage).not.toContain("eyJ");
  });

  test("the api proxy calls the api as the signed-in user", async ({ page }) => {
    await page.goto("/");

    const me = await page.evaluate(async () => (await fetch("/api/v1/me")).json());

    expect(me.display_name).toBe("Cleo Commander");
    expect(me.permissions).toContain("approve_remediation");
  });

  test("cross-site state-changing requests are rejected", async ({ page }) => {
    await page.goto("/");

    const response = await page.request.post("/api/v1/me", {
      headers: { Origin: "https://evil.example" },
    });

    expect(response.status()).toBe(403);
  });

})

test.describe("sign out", () => {
  // Uses its own session so signing out cannot affect tests sharing the saved one.
  test.use({ storageState: { cookies: [], origins: [] } });

  test("sign out ends the session everywhere", async ({ page, browser, context }) => {
    await signIn(page, "operator");
    const before = await context.cookies();

    await page.getByRole("button", { name: "Sign out" }).click();

    await expect(page).toHaveURL(/\/login\?signed_out=1$/);
    await expect(page.getByRole("status")).toHaveText("You have been signed out.");

    // Replaying the old session cookie must not work: the server-side session is gone.
    const replay = await browser.newContext();
    await replay.addCookies(before);
    const replayPage = await replay.newPage();
    await replayPage.goto("/");
    await expect(replayPage).toHaveURL(/\/login/);
    await replay.close();
  });
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("shows only the viewer role", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("list", { name: "Your roles" })).toHaveText("Viewer");
    await expect(page.getByText("Incident commander")).toHaveCount(0);
  });
});
