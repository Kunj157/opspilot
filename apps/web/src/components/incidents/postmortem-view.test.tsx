import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";

import { PostmortemView } from "./postmortem-view";

const READY = {
  id: "pm-1",
  status: "ready",
  generated_by: "ollama:qwen2.5:7b-instruct",
  prompt_version: "v1",
  updated_at: "2026-10-14T02:00:00Z",
  content: {
    summary: "Release 1.4.2 broke checkout.",
    impact: "Half of checkouts failed for 12 minutes.",
    root_cause: {
      statement: "Release 1.4.2 introduced a regression",
      certainty: "strong_hypothesis",
      evidence: ["E2"],
    },
    findings: [
      { statement: "Error rate reached 45%", certainty: "confirmed", evidence: ["E1"] },
      { statement: "Why 1.4.2 fails", certainty: "unknown", evidence: [] },
    ],
    resolution: "Rolled back to 1.0.0.",
    follow_ups: ["Add a canary stage"],
    timeline: [{ at: "2026-10-14T01:16:00Z", event: "Incident detected", actor: "system:detector" }],
    evidence: {
      E1: { summary: "error rate 45%", source: "prometheus" },
      E2: { summary: "revision 20", source: "kubernetes" },
    },
  },
};

function serve(get: { status: number; body: unknown }, post?: unknown) {
  const fetchMock = vi.fn(async (input: Request | string) => {
    const request = typeof input === "string" ? new Request(input) : input;
    const body = request.method === "POST" ? post : get.body;
    return new Response(JSON.stringify(body), {
      status: request.method === "POST" ? 202 : get.status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderIt(canManage: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <PostmortemView incidentId="i-1" canManage={canManage} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("PostmortemView", () => {
  it("labels each finding's certainty and shows its citations", async () => {
    serve({ status: 200, body: READY });
    renderIt(false);

    expect(await screen.findByText("Release 1.4.2 broke checkout.")).toBeInTheDocument();
    const findings = screen.getByRole("list", { name: "Findings" });
    const [confirmed, unknown] = within(findings).getAllByRole("listitem");
    expect(confirmed).toHaveTextContent("Confirmed");
    expect(confirmed).toHaveTextContent("E1 prometheus");
    expect(unknown).toHaveTextContent("Unknown");
    expect(screen.getByText("Strong hypothesis")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("lets incident managers request a draft", async () => {
    const user = userEvent.setup();
    serve({ status: 404, body: { detail: "No postmortem yet" } }, { ...READY, status: "pending", content: null });
    renderIt(true);

    await user.click(await screen.findByRole("button", { name: "Draft postmortem" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Drafting the postmortem");
  });
});
