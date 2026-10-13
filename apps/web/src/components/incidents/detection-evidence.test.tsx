import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DetectionEvidence } from "./detection-evidence";

function detection(outcome: string, errorRate: number, end: string, rps = 4.9, service = "svc-checkout") {
  return {
    id: `${outcome}-${end}-${service}`,
    service_id: service,
    detector: "error-rate",
    failure_category: "high_error_rate",
    outcome,
    score: errorRate / 0.05,
    threshold: 0.05,
    features: { error_rate: errorRate, requests_per_second: rps },
    model_version: "rule-v1",
    window_start: end,
    window_end: end,
    created_at: end,
  };
}

function serve(items: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ items }), { headers: { "Content-Type": "application/json" } })),
  );
}

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DetectionEvidence
        incidentId="i-1"
        serviceId="svc-checkout"
        serviceNames={new Map([["svc-checkout", "Checkout"], ["svc-storefront", "Storefront"]])}
      />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("DetectionEvidence", () => {
  it("summarises the latest reading against the threshold", async () => {
    serve([
      detection("ongoing", 0.449, "2026-10-14T12:02:00Z", 1.1),
      detection("triggered", 0.31, "2026-10-14T12:01:00Z"),
    ]);
    renderIt();

    expect(await screen.findByText("44.9% of requests failing, 9.0× the 5% threshold")).toBeInTheDocument();
    const panel = screen.getByRole("region", { name: "Detection" });
    expect(within(panel).getByRole("group", { name: "Peak error rate" })).toHaveTextContent("44.9%");
    expect(within(panel).getByRole("group", { name: "Traffic" })).toHaveTextContent("1.1 req/s");
    expect(within(panel).getByRole("group", { name: "Rule" })).toHaveTextContent("error-rate · rule-v1");
  });

  it("lists recent decisions with readable outcomes", async () => {
    serve([
      detection("recovered", 0, "2026-10-14T12:03:00Z"),
      detection("ongoing", 0.4, "2026-10-14T12:02:00Z"),
      detection("triggered", 0.3, "2026-10-14T12:01:00Z"),
    ]);
    renderIt();

    const list = await screen.findByRole("list", { name: "Detector readings" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      expect.stringContaining("Recovered"),
      expect.stringContaining("Still failing"),
      expect.stringContaining("Triggered"),
    ]);
    expect(screen.getByRole("region", { name: "Detection" })).toHaveTextContent("Error rate back to 0.0%");
  });

  it("keeps affected callers out of the summary and labels their readings", async () => {
    serve([
      detection("ongoing", 0.1, "2026-10-14T12:02:00Z", 5, "svc-storefront"),
      detection("ongoing", 0.5, "2026-10-14T12:02:00Z"),
      detection("triggered", 0.3, "2026-10-14T12:01:00Z", 5, "svc-storefront"),
      detection("triggered", 0.45, "2026-10-14T12:01:00Z"),
    ]);
    renderIt();

    expect(await screen.findByText("50.0% of requests failing, 10.0× the 5% threshold")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Peak error rate" })).toHaveTextContent("50.0%");
    const items = within(screen.getByRole("list", { name: "Detector readings" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Storefront (affected)");
    expect(items[1]).not.toHaveTextContent("affected");
  });

  it("explains when no readings are recorded", async () => {
    serve([]);
    renderIt();

    expect(await screen.findByText(/no detector readings recorded/i)).toBeInTheDocument();
  });
});
