import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";

import { type Proposal, RemediationReview } from "./remediation-review";

const NOW = new Date("2026-10-14T01:20:00Z").getTime();

const pending: Proposal = {
  id: "p-1",
  action_type: "ROLLBACK_DEPLOYMENT",
  description: "Errors began with release 1.4.2",
  parameters: { namespace: "demo", deployment: "checkout", to_revision: 23, from_version: "1.4.2", to_version: "1.0.0" },
  risk_level: "medium",
  status: "PENDING",
  verification_plan: { window_minutes: 3, max_error_rate: 0.02, max_p95_ratio_to_baseline: 1.5 },
  evidence_ids: ["e2"],
  runbook_id: null,
  version: 3,
  expires_at: "2026-10-14T01:46:00Z",
  created_at: "2026-10-14T01:16:10Z",
  decision: null,
  execution: null,
};

const verified: Proposal = {
  ...pending,
  status: "EXECUTED",
  decision: {
    decision: "approved",
    proposal_version: 3,
    reviewed_by: "u-1",
    reviewer_name: "Cleo Commander",
    comment: "Errors began with 1.4.2",
    reviewed_at: "2026-10-14T01:17:00Z",
  },
  execution: {
    id: "x-1",
    status: "succeeded",
    attempts: 1,
    started_at: "2026-10-14T01:17:01Z",
    completed_at: "2026-10-14T01:17:02Z",
    output: { rolled_back_to: 23, version: "1.0.0" },
    error_message: null,
    verification_status: "passed",
    verification: { reason: "error rate 0.0%, p95 24 ms" },
    verified_at: "2026-10-14T01:20:20Z",
  },
};

function renderIt(proposal: Proposal, canApprove: boolean, onDecided = vi.fn()) {
  render(
    <ToastProvider>
      <RemediationReview proposal={proposal} refs={new Map([["e2", "E2"]])} canApprove={canApprove} now={NOW} onDecided={onDecided} />
    </ToastProvider>,
  );
  return onDecided;
}

function serve(status: number, body: unknown) {
  const fetchMock = vi.fn<(input: Request) => Promise<Response>>(
    async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("RemediationReview", () => {
  it("shows the action, versions, verification plan, expiry, and cited evidence", () => {
    renderIt(pending, false);

    const card = screen.getByRole("region", { name: "Proposed remediation" });
    expect(card).toHaveTextContent("Roll back checkout to revision 23");
    expect(card).toHaveTextContent("1.4.2 → 1.0.0");
    expect(card).toHaveTextContent("error rate ≤ 2%, p95 ≤ 1.5× baseline over 3 min");
    expect(card).toHaveTextContent("Expires in 26 min");
    expect(within(card).getByRole("link", { name: "E2" })).toHaveAttribute("href", "#evidence-e2");
  });

  it("is read-only for people who cannot approve", () => {
    renderIt(pending, false);

    expect(screen.getByText("Awaiting approval by an incident commander")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve and run" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });

  it("approves the version on screen with the comment", async () => {
    const user = userEvent.setup();
    const fetchMock = serve(200, { ...pending, status: "APPROVED" });
    const onDecided = renderIt(pending, true);

    await user.type(screen.getByLabelText("Comment (recorded with your decision)"), "Roll back now");
    await user.click(screen.getByRole("button", { name: "Approve and run" }));

    const request = fetchMock.mock.calls[0][0];
    expect(new URL(request.url).pathname).toBe("/api/v1/proposals/p-1/approve");
    expect(await request.json()).toEqual({ version: 3, comment: "Roll back now" });
    expect(await screen.findByText("Approved: the worker runs it now")).toBeInTheDocument();
    expect(onDecided).toHaveBeenCalled();
  });

  it("explains a refused decision", async () => {
    const user = userEvent.setup();
    serve(409, { detail: "The proposal changed since you reviewed it (version 3, now 4); review it again" });
    renderIt(pending, true);

    await user.click(screen.getByRole("button", { name: "Reject" }));

    expect(await screen.findByText(/changed since you reviewed it/)).toBeInTheDocument();
  });

  it("offers no decision on an expired proposal", () => {
    renderIt({ ...pending, expires_at: "2026-10-14T01:19:00Z" }, true);

    expect(screen.queryByRole("button", { name: "Approve and run" })).not.toBeInTheDocument();
    expect(screen.getByText("Expired; run the agents again for a fresh proposal")).toBeInTheDocument();
  });

  it("follows approval, execution, and verification", () => {
    renderIt(verified, true);

    const progress = screen.getByRole("list", { name: "Remediation progress" });
    const steps = within(progress).getAllByRole("listitem").map((li) => li.textContent);
    expect(steps[1]).toContain("Approved by Cleo Commander");
    expect(steps[1]).toContain("Errors began with 1.4.2");
    expect(steps[2]).toContain("Executed (1.0.0)");
    expect(steps[3]).toContain("Recovery verified");
    expect(steps[3]).toContain("error rate 0.0%, p95 24 ms");
    expect(screen.queryByRole("button", { name: "Approve and run" })).not.toBeInTheDocument();
  });

  it("shows a failed verification", () => {
    renderIt(
      {
        ...verified,
        execution: { ...verified.execution!, verification_status: "failed", verification: { reason: "error rate 30.0% is above 2%" } },
      },
      true,
    );

    expect(screen.getByText("Verification failed; investigating again")).toBeInTheDocument();
    expect(screen.getByText("error rate 30.0% is above 2%")).toBeInTheDocument();
  });
});
