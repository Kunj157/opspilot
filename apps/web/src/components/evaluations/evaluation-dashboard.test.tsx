import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { costPerInvestigation, EvaluationDashboard, parseRange } from "./evaluation-dashboard";

const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace }),
  usePathname: () => "/evaluations",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

const DATA = {
  range_start: "2026-09-14T00:00:00Z",
  range_end: "2026-10-14T00:00:00Z",
  detection: { incidents: 12, delay_p50_seconds: 95, delay_p95_seconds: 240 },
  investigations: { total: 10, succeeded: 7, partial: 2, failed: 1 },
  agents: { runs: 40, success_rate: 0.9, tool_calls: 200, tool_error_rate: 0.05, input_tokens: 120000, output_tokens: 30000, cost_usd: 1.5 },
  remediation: { decisions: 8, approval_rate: 0.75 },
  response: { mtta_seconds: 300, mttr_seconds: 3600 },
};

const requests: URL[] = [];

beforeEach(() => {
  navigation.search = "";
  navigation.replace.mockReset();
  requests.length = 0;
  // Reduced motion: numbers render their final values at once.
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), media: query, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      requests.push(new URL(input.url));
      return new Response(JSON.stringify(DATA), { headers: { "Content-Type": "application/json" } });
    }),
  );
});

function renderIt() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EvaluationDashboard />
    </QueryClientProvider>,
  );
}

describe("evaluation helpers", () => {
  it("accepts only the offered ranges", () => {
    expect(parseRange("7")).toBe(7);
    expect(parseRange("90")).toBe(90);
    expect(parseRange("13")).toBe(30);
    expect(parseRange(null)).toBe(30);
  });

  it("divides cost by investigations, or has none", () => {
    expect(costPerInvestigation(DATA as never)).toBeCloseTo(0.15);
    expect(costPerInvestigation({ ...DATA, investigations: { ...DATA.investigations, total: 0 } } as never)).toBeNull();
  });
});

describe("EvaluationDashboard", () => {
  it("shows agent, investigation, detection, and remediation metrics", async () => {
    renderIt();

    expect(within(await screen.findByRole("group", { name: "Agent success rate" })).getByText("90%")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Tool-call accuracy" })).toHaveTextContent("95%");
    expect(screen.getByRole("group", { name: "Investigation success rate" })).toHaveTextContent("70%");
    expect(screen.getByRole("group", { name: "Cost per investigation" })).toHaveTextContent("$0.15");
    expect(screen.getByRole("group", { name: "Detection delay p50" })).toHaveTextContent("1m");
    expect(screen.getByRole("group", { name: "Approval rate" })).toHaveTextContent("75%");
    expect(screen.getByRole("list", { name: "Investigation outcomes" })).toHaveTextContent(/Completed\s*7.*Stopped early\s*2.*Failed\s*1/);
  });

  it("asks for the last 30 days by default and switches range through the URL", async () => {
    const user = userEvent.setup();
    renderIt();
    await screen.findByRole("group", { name: "Agent success rate" });

    const call = requests.find((u) => u.pathname === "/api/v1/evaluations")!;
    const span = Date.parse(call.searchParams.get("to")!) - Date.parse(call.searchParams.get("from")!);
    expect(Math.round(span / 86_400_000)).toBe(30);

    await user.click(screen.getByRole("button", { name: "7d" }));
    expect(navigation.replace).toHaveBeenCalledWith("/evaluations?days=7", { scroll: false });
  });
});
