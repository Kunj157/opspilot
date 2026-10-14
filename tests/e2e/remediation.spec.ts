import { execFileSync } from "node:child_process";

import { expect, type Playwright, test } from "@playwright/test";

import { AUTH_DIR } from "./support";

/** A new incident awaiting approval of a rollback proposal (created as the commander). */
async function awaitingApproval(playwright: Playwright, baseURL: string) {
  const api = await playwright.request.newContext({ baseURL, storageState: `${AUTH_DIR}/commander.json` });
  const created = await api.post("/api/v1/incidents", {
    headers: { Origin: baseURL },
    data: { title: `Remediation ${Date.now()}`, severity: "critical" },
  });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  await api.dispose();
  execFileSync("uv", ["run", "--directory", "apps/api", "python", "../../tests/e2e/fixtures/seed_proposal.py", id]);
  return id;
}

test("an incident commander approves a rollback and follows it", async ({ page, baseURL, playwright }) => {
  const id = await awaitingApproval(playwright, baseURL!);
  await page.goto(`/incidents/${id}`);

  const card = page.getByRole("region", { name: "Proposed remediation" });
  await expect(card).toContainText("Roll back checkout to revision 6");
  await expect(card).toContainText("Awaiting your decision");
  await card.getByLabel("Comment (recorded with your decision)").fill("Errors began with 1.4.2");
  await card.getByRole("button", { name: "Approve and run" }).click();

  await expect(page.getByRole("region", { name: "Notifications" })).toContainText("Approved: the worker runs it now");
  const progress = card.getByRole("list", { name: "Remediation progress" });
  await expect(progress).toContainText("Approved by");
  await expect(progress).toContainText("Errors began with 1.4.2");
  await expect(progress).toContainText("Executing…");
  await expect(card.getByRole("button", { name: "Approve and run" })).toHaveCount(0);
  // The status change arrives over the live stream.
  await expect(page.getByRole("list", { name: "Timeline" })).toContainText("Awaiting Approval → Remediating");
});

test("a rejected proposal stays rejected", async ({ page, baseURL, playwright }) => {
  const id = await awaitingApproval(playwright, baseURL!);
  await page.goto(`/incidents/${id}`);

  const card = page.getByRole("region", { name: "Proposed remediation" });
  await card.getByRole("button", { name: "Reject" }).click();

  await expect(card.getByRole("list", { name: "Remediation progress" })).toContainText("Rejected by");
  await expect(card.getByRole("button")).toHaveCount(0);
});

test.describe("as a viewer", () => {
  test.use({ storageState: `${AUTH_DIR}/viewer.json` });

  test("the proposal is shown read-only", async ({ page, baseURL, playwright }) => {
    const id = await awaitingApproval(playwright, baseURL!);
    await page.goto(`/incidents/${id}`);

    const card = page.getByRole("region", { name: "Proposed remediation" });
    await expect(card).toContainText("Awaiting approval by an incident commander");
    await expect(card.getByRole("button")).toHaveCount(0);
  });
});
