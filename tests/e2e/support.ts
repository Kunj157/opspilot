import { expect, type Page } from "@playwright/test";

export const AUTH_DIR = "playwright/.auth";
export const PASSWORD = "opspilot-dev";

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
