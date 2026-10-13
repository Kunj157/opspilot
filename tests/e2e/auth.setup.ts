import { test as setup } from "@playwright/test";

import { AUTH_DIR, signIn } from "./support";

for (const user of ["commander", "viewer"]) {
  setup(`sign in as ${user}`, async ({ page }) => {
    await signIn(page, user);
    await page.context().storageState({ path: `${AUTH_DIR}/${user}.json` });
  });
}
