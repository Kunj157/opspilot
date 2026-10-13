import { expect, type Page } from "@playwright/test";

export const AUTH_DIR = "playwright/.auth";
export const PASSWORD = "opspilot-dev";

// Keycloak brute-force protection treats near-simultaneous logins of one
// account as an attack and locks it briefly. Each test that signs in
// interactively therefore uses its own user:
//   setup → commander, viewer · sign-in → commander (after setup)
//   return-to → viewer (after setup) · off-site return → admin · sign-out → operator

/** Signs in through the real Keycloak login page, starting from wherever the app sent us. */
export async function signInOnKeycloak(page: Page, username: string) {
  await expect(page).toHaveURL(/\/realms\/opspilot\/protocol\/openid-connect\/auth/);
  await page.getByLabel("Username or email").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
}

export async function signIn(page: Page, username: string, path = "/") {
  await page.goto(path);
  await page.getByRole("link", { name: "Continue with single sign-on" }).click();
  await signInOnKeycloak(page, username);
  await expect(page.getByTestId("user-name")).toBeVisible();
}
