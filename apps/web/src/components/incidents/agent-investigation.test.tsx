import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";

import { AgentInvestigation } from "./agent-investigation";

const investigation = {
  id: "inv-1",
  incident_id: "i-1",
  status: "completed",
  current_node: "remediation",
  round: 0,
  result: {
    summary: "Release 1.4.2 broke checkout.",
    hypotheses: [
      {
        description: "Release 1.4.2 introduced a regression",
        confidence: 0.82,
        supporting_evidence: ["E2", "E3"],
        contradicting_evidence: [],
      },
    ],
    unknowns: ["Why 1.4.2 fails"],
    proposal_id: "p-1",
    runbooks: [
      {
        slug: "checkout-high-error-rate",
        title: "Checkout high error rate",
        version: 1,
        runbook_id: "rb-1",
        score: 0.93,
      },
    ],
    notes: [],
    manual_review: false,
  },
  error: null,
  tool_calls: 7,
  input_tokens: 4200,
  output_tokens: 600,
  cost_usd: 0,
  created_at: "2026-10-14T01:16:00Z",
  started_at: "2026-10-14T01:16:01Z",
  completed_at: "2026-10-14T01:16:11Z",
};

const evidence = [
  {
    id: "e1",
    evidence_type: "topology",
    source: "service catalog",
    summary: "Checkout calls payment",
    content: {},
    query: "dependencies of checkout",
    time_range_start: null,
    time_range_end: "2026-10-14T01:16:02Z",
    confidence: 0.9,
    created_at: "2026-10-14T01:16:02Z",
  },
  {
    id: "e2",
    evidence_type: "metrics",
    source: "prometheus",
    summary: "Checkout: error rate 29.1%",
    content: {},
    query: "sum(rate(...))",
    time_range_start: "2026-10-14T01:01:00Z",
    time_range_end: "2026-10-14T01:16:00Z",
    confidence: 0.9,
    created_at: "2026-10-14T01:16:03Z",
  },
  {
    id: "e3",
    evidence_type: "deployment",
    source: "kubernetes",
    summary: "revision 20 (1.4.2) rolled out 1 minute ago",
    content: {},
    query: "rollout history",
    time_range_start: null,
    time_range_end: null,
    confidence: 0.95,
    created_at: "2026-10-14T01:16:04Z",
  },
];

const proposal = {
  id: "p-1",
  action_type: "ROLLBACK_DEPLOYMENT",
  description: "Errors began with release 1.4.2",
  parameters: {
    namespace: "demo",
    deployment: "checkout",
    to_revision: 19,
    from_version: "1.4.2",
    to_version: "1.0.0",
  },
  risk_level: "medium",
  status: "PENDING",
  verification_plan: { window_minutes: 5, max_error_rate: 0.02 },
  evidence_ids: ["e2", "e3"],
  runbook_id: "rb-1",
  version: 1,
  expires_at: "2099-10-14T01:46:00Z",
  created_at: "2026-10-14T01:16:10Z",
};

function serve(routes: Record<string, { status?: number; body: unknown }>) {
  const fetchMock = vi.fn(async (input: Request | string) => {
    const request = typeof input === "string" ? new Request(input) : input;
    const path = new URL(request.url).pathname.replace("/api/v1/incidents/i-1", "");
    const route = routes[`${request.method} ${path}`] ?? { status: 404, body: { detail: "Not Found" } };
    return new Response(JSON.stringify(route.body), {
      status: route.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderIt(canInvestigate = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentInvestigation incidentId="i-1" canInvestigate={canInvestigate} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const full = {
  "GET /investigation": { body: investigation },
  "GET /evidence": { body: { items: evidence } },
  "GET /proposals": { body: { items: [proposal] } },
  "GET /agent-runs": { body: { items: [] } },
};

afterEach(() => vi.unstubAllGlobals());

describe("AgentInvestigation", () => {
  it("shows hypotheses with confidence and links to the cited evidence", async () => {
    serve(full);
    renderIt();

    const panel = await screen.findByRole("region", { name: "Agent investigation" });
    expect(await within(panel).findByText("Release 1.4.2 broke checkout.")).toBeInTheDocument();
    const hypotheses = within(panel).getByRole("list", { name: "Hypotheses" });
    expect(hypotheses).toHaveTextContent("82%");
    const cite = within(hypotheses).getByRole("link", { name: "E2" });
    expect(cite).toHaveAttribute("href", "#evidence-e2");
    expect(within(panel).getByText("Why 1.4.2 fails")).toBeInTheDocument();
  });

  it("presents the proposal as awaiting approval, read-only", async () => {
    serve(full);
    renderIt();

    const card = await screen.findByRole("region", { name: "Proposed remediation" });
    expect(card).toHaveTextContent("Roll back checkout");
    expect(card).toHaveTextContent("1.4.2 → 1.0.0");
    expect(card).toHaveTextContent("Awaiting approval");
    expect(card).toHaveTextContent("medium risk");
  });

  it("lists cited evidence with source and query", async () => {
    serve(full);
    renderIt();

    const list = await screen.findByRole("list", { name: "Evidence" });
    const second = within(list).getAllByRole("listitem")[1];
    expect(second).toHaveAttribute("id", "evidence-e2");
    expect(second).toHaveTextContent("E2");
    expect(second).toHaveTextContent("prometheus");
    expect(second).toHaveTextContent("sum(rate(...))");
  });

  it("offers to start an investigation when there is none", async () => {
    const user = userEvent.setup();
    const fetchMock = serve({
      "GET /evidence": { body: { items: [] } },
      "GET /proposals": { body: { items: [] } },
      "GET /agent-runs": { body: { items: [] } },
      "POST /investigation": { status: 202, body: { ...investigation, status: "queued", result: null } },
    });
    renderIt();

    await user.click(await screen.findByRole("button", { name: "Run agent investigation" }));

    const posted = fetchMock.mock.calls.map(([r]) => r as Request).find((r) => r.method === "POST");
    expect(posted?.url).toContain("/api/v1/incidents/i-1/investigation");
  });

  it("explains a partial investigation and hides the start button without permission", async () => {
    serve({
      ...full,
      "GET /investigation": {
        body: {
          ...investigation,
          status: "partial",
          error: "tool call limit reached",
          result: { ...investigation.result, manual_review: true, hypotheses: [] },
        },
      },
      "GET /proposals": { body: { items: [] } },
    });
    renderIt(false);

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent(/stopped early: tool call limit reached/i);
    expect(notice).toHaveTextContent(/manual review recommended/i);
    expect(screen.queryByRole("button", { name: /investigation/i })).not.toBeInTheDocument();
  });
});
