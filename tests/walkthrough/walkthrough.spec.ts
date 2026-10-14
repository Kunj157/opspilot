import { execSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";

import { type Browser, type BrowserContext, expect, type Page, test } from "@playwright/test";

import { signIn } from "../e2e/support";

// The real incident loop on the kind demo, recorded scene by scene. Waits
// between scenes (detection, investigation, verification) happen off camera:
// each scene is its own clip in walkthrough-output/, plus shot-list.md with
// what each clip shows, for narration.

const OUT = "walkthrough-output";
const API = `http://127.0.0.1:${process.env.API_PORT ?? "8000"}/api/v1`;
const SCENARIO = process.env.WALKTHROUGH_SCENARIO ?? "checkout-http-500";
const SIZE = { width: 1440, height: 900 };

test.describe.configure({ mode: "serial" });

type Shot = { clip: string; title: string; notes: string[] };
let state = "";
let token = "";
let incidentId = "";

const freshToken = () => execSync("make -s token USER=commander", { encoding: "utf8" }).trim();

// Access tokens live for minutes and the loop takes longer: refresh on 401.
async function api<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...init.headers },
  });
  if (r.status === 401 && !retried) {
    token = freshToken();
    return api(path, init, true);
  }
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

const ALL_STATUSES = ["DETECTED", "INVESTIGATING", "AWAITING_APPROVAL", "REMEDIATING", "VERIFYING", "MONITORING", "RESOLVED"]
  .map((st) => `status=${st}`)
  .join("&");

/** Re-recording later scenes alone (-g "05|06") picks up the latest detector incident. */
async function currentIncident(): Promise<string> {
  if (incidentId) return incidentId;
  const page = await api<{ items: { id: string }[] }>(`/incidents?source=detector&limit=1&${ALL_STATUSES}`);
  incidentId = page.items[0]?.id ?? "";
  if (!incidentId) throw new Error("no detector incident: record from scene 02");
  return incidentId;
}

async function until<T>(what: string, probe: () => Promise<T | undefined>, timeoutMs: number): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = await probe().catch(() => undefined);
    if (value) return value;
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 5_000));
  }
}

// Headless browsers draw no pointer; show one so viewers can follow the clicks.
const CURSOR = `
  addEventListener("DOMContentLoaded", () => {
    const dot = document.createElement("div");
    dot.style.cssText = "position:fixed;z-index:2147483647;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(167,139,250,.55);box-shadow:0 0 0 2px rgba(255,255,255,.85);pointer-events:none;transition:transform .12s;left:-40px;top:-40px";
    document.body.appendChild(dot);
    addEventListener("mousemove", (e) => { dot.style.left = e.clientX + "px"; dot.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => { dot.style.transform = "scale(.7)"; }, true);
    addEventListener("mouseup", () => { dot.style.transform = "scale(1)"; }, true);
  });`;

async function scene(browser: Browser, clip: string, title: string, notes: string[], body: (page: Page) => Promise<void>) {
  const context: BrowserContext = await browser.newContext({
    storageState: state,
    viewport: SIZE,
    recordVideo: { dir: `${OUT}/raw`, size: SIZE },
  });
  await context.addInitScript(CURSOR);
  const page = await context.newPage();
  await body(page);
  await beat(page, 1_500);
  const video = page.video();
  await context.close();
  await video?.saveAs(`${OUT}/${clip}.webm`);
  writeFileSync(`${OUT}/raw/${clip}.json`, JSON.stringify({ clip, title, notes }));
}

const beat = (page: Page, ms = 1_200) => page.waitForTimeout(ms);

/** Moves the visible pointer to an element, then clicks it. */
async function point(page: Page, locator: ReturnType<Page["locator"]>, click = true) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 25 });
  await beat(page, 400);
  if (click) await locator.click();
}

test.beforeAll(async ({ browser }) => {
  mkdirSync(`${OUT}/raw`, { recursive: true });
  token = freshToken();
  const context = await browser.newContext({ viewport: SIZE });
  const page = await context.newPage();
  await signIn(page, "commander");
  state = `${OUT}/raw/commander.json`;
  await context.storageState({ path: state });
  await context.close();
});

test.afterAll(() => {
  const shots = readdirSync(`${OUT}/raw`)
    .filter((f) => /^\d\d-.*\.json$/.test(f))
    .sort()
    .map((f) => JSON.parse(readFileSync(`${OUT}/raw/${f}`, "utf8")) as Shot);
  const lines = ["# Walkthrough shot list", "", "Clips in this folder, in order. Times are real; waits happen between clips.", ""];
  for (const s of shots) lines.push(`## ${s.clip}: ${s.title}`, "", ...s.notes.map((n) => `- ${n}`), "");
  writeFileSync(`${OUT}/shot-list.md`, lines.join("\n"));
});

test("01 command center", async ({ browser }) => {
  await scene(
    browser,
    "01-command-center",
    "A healthy system",
    [
      "The command center: open incidents, MTTA and MTTR counting up, service health, live alert stream.",
      "The 3D service topology of the demo shop: storefront, checkout, payment, inventory, notification.",
      "Cmd-K opens the command palette; 'checkout' → show it on the map, the camera flies to the service.",
    ],
    async (page) => {
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await beat(page, 4_000);
      await page.getByText("Service topology").first().scrollIntoViewIfNeeded();
      await page.mouse.wheel(0, 250);
      await beat(page, 3_000);
      await page.mouse.move(600, 600, { steps: 40 });
      await beat(page, 2_000);
      await page.keyboard.press("Control+k");
      const palette = page.getByRole("dialog", { name: "Command palette" });
      await expect(palette).toBeVisible();
      await palette.getByRole("combobox").pressSequentially("checkout", { delay: 120 });
      await beat(page, 1_000);
      const onMap = palette.getByRole("option", { name: "Show Checkout on the map" });
      if (await onMap.count()) await point(page, onMap);
      else await page.keyboard.press("Escape");
      await beat(page, 800);
      const topology = page.getByText("Service topology").first();
      await topology.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "start" }));
      await beat(page, 7_000);
    },
  );
});

test("02 a faulty release is detected", async ({ browser }) => {
  execSync(`make inject-failure SCENARIO=${SCENARIO}`, { stdio: "inherit" });
  const started = Date.now();
  const incident = await until(
    "the detector to open an incident",
    async () => {
      const page = await api<{ items: { id: string; source: string; created_at: string }[] }>(
        "/incidents?source=detector&limit=5",
      );
      return page.items.find((i) => new Date(i.created_at).getTime() > started - 60_000);
    },
    6 * 60_000,
  );
  incidentId = incident.id;
  await scene(
    browser,
    "02-detection",
    "Detection opens one incident",
    [
      `A faulty checkout release (${SCENARIO}) was shipped; the detector saw a sustained error-rate breach.`,
      `Detected ${Math.round((Date.now() - started) / 1000)} s after the release.`,
      "Exactly one incident on the failing service; callers are noted as affected.",
    ],
    async (page) => {
      await page.goto("/incidents");
      await beat(page, 3_000);
      await point(page, page.getByRole("link").filter({ hasText: /checkout/i }).first());
      await expect(page).toHaveURL(new RegExp(incidentId));
      await beat(page, 3_000);
      const detection = page.getByText(/detect/i).first();
      if (await detection.count()) await point(page, detection, false);
      await beat(page, 4_000);
    },
  );
});

test("03 agents investigate", async ({ browser }) => {
  await currentIncident();
  await scene(
    browser,
    "03-investigation",
    "Agents investigate",
    [
      "LangGraph agents: triage → observability → deployments → runbooks → synthesis → remediation.",
      "Read-only tools over Prometheus, Loki, Tempo, Kubernetes, the catalog, and the runbook library.",
      "Hypotheses cite collected evidence; the matching runbook is read in full; a rollback is proposed.",
    ],
    async (page) => {
      await page.goto(`/incidents/${incidentId}`);
      await beat(page, 2_000);
      // Watch the agents work live (the panel updates over SSE).
      const panel = page.getByText("Agent investigation").first();
      await panel.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "start" }));
      await beat(page, 1_500);
      await until(
        "the investigation to finish",
        async () => {
          const run = await api<{ status: string } | null>(`/incidents/${incidentId}/investigation`);
          return run && ["completed", "partial", "failed"].includes(run.status) ? run : undefined;
        },
        8 * 60_000,
      );
      await beat(page, 3_000);
      await panel.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "start" }));
      await beat(page, 3_000);
      for (const name of [/hypothes/i, /evidence/i, /tool/i, /runbook/i]) {
        const tab = page.getByRole("tab", { name }).first();
        if (await tab.count()) {
          await point(page, tab);
          await beat(page, 3_000);
        }
      }
    },
  );
});

test("04 approval and rollback", async ({ browser }) => {
  await currentIncident();
  await scene(
    browser,
    "04-approval",
    "An incident commander approves",
    [
      "The proposal: rollback to the previous release, risk level, policy checks, evidence.",
      "Approving binds to this exact proposal version; the worker runs it once.",
    ],
    async (page) => {
      await page.goto(`/incidents/${incidentId}`);
      const card = page.getByRole("region", { name: "Proposed remediation" });
      await expect(card).toBeVisible({ timeout: 60_000 });
      await point(page, card, false);
      await beat(page, 4_000);
      await point(page, card.getByRole("button", { name: "Approve and run" }));
      await beat(page, 6_000);
    },
  );
});

test("05 recovery and postmortem", async ({ browser }) => {
  await currentIncident();
  await until(
    "the incident to resolve",
    async () => {
      const incident = await api<{ status: string }>(`/incidents/${incidentId}`);
      return incident.status === "RESOLVED" ? incident : undefined;
    },
    10 * 60_000,
  );
  await api(`/incidents/${incidentId}/postmortem`, { method: "POST", body: "{}" }).catch(() => undefined);
  await until("the postmortem draft", () => api(`/incidents/${incidentId}/postmortem`), 5 * 60_000);
  await scene(
    browser,
    "05-resolution",
    "Recovery verified, postmortem drafted",
    [
      "Rollout complete; error rate and p95 compared with the pre-incident baseline; resolved.",
      "The timeline tells the whole story, every step audited.",
      "A blameless postmortem whose findings are labelled confirmed, hypothesis, or unknown, each citing evidence.",
    ],
    async (page) => {
      await page.goto(`/incidents/${incidentId}`);
      await beat(page, 3_000);
      const timeline = page.getByRole("list", { name: "Timeline" });
      if (await timeline.count()) await point(page, timeline, false);
      await page.mouse.wheel(0, 900);
      await beat(page, 3_000);
      const postmortem = page.getByRole("tab", { name: /postmortem/i }).first();
      if (await postmortem.count()) await point(page, postmortem);
      await beat(page, 3_000);
      await page.mouse.wheel(0, 1_200);
      await beat(page, 4_000);
    },
  );
});

test("06 evidence of operation", async ({ browser }) => {
  await scene(
    browser,
    "06-evaluations-audit-ml",
    "Evaluations, audit log, ML detector",
    [
      "Evaluations: detection delay, investigation outcomes, tool errors, tokens and cost, approval rate, MTTA, MTTR.",
      "Audit log: every user, agent, and system action, append-only.",
      "ML detector in shadow mode next to the rule-based baseline.",
    ],
    async (page) => {
      for (const path of ["/evaluations", "/audit-logs", "/models"]) {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await beat(page, 2_500);
        await page.mouse.wheel(0, 700);
        await beat(page, 2_500);
      }
    },
  );
  execSync("make reset-demo", { stdio: "inherit" });
});
