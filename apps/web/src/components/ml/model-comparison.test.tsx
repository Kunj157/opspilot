import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";

import { ModelComparison } from "./model-comparison";

const metrics = {
  model: { precision: 0.91, recall: 0.84, f1: 0.87, false_alerts_per_hour: 0.4, median_detection_delay_s: 45, p95_detection_delay_s: 60, missed_incidents: 0, inference_ms_per_window: 0.8 },
  baseline: { precision: 0.95, recall: 0.62, f1: 0.75, false_alerts_per_hour: 0.2, median_detection_delay_s: 75, p95_detection_delay_s: 90, missed_incidents: 1, inference_ms_per_window: 0.3 },
  promotable: true,
  reason: "beats or complements the baseline",
  test: { runs: [5, 6], scenarios: ["checkout-http-500", "checkout-latency"] },
};
const shadowModel = {
  id: "m-2", name: "isolation-forest", version: 2, status: "shadow", feature_schema: { version: "v1", features: ["request_rate", "error_rate"] },
  metrics, mlflow_run_id: "abc", created_at: "2026-10-14T05:00:00Z", promoted_at: "2026-10-14T05:01:00Z",
};
const oldModel = { ...shadowModel, id: "m-1", version: 1, status: "retired" };
const shadow = {
  since: "2026-10-13T05:00:00Z",
  model: "isolation-forest:2",
  features: ["request_rate"],
  services: [{ service_id: "s-1", service: "Checkout", shadow_windows: 5760, shadow_alerts: 18, rule_triggers: 2, incidents: 2 }],
};

function serve(routes: Record<string, { status?: number; body: unknown }>) {
  const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async (request) => {
    const url = new URL(request.url);
    const route = routes[`${request.method} ${url.pathname}`] ?? { status: 404, body: { detail: "Not Found" } };
    return new Response(JSON.stringify(route.body), { status: route.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderIt(canManage: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ModelComparison canManage={canManage} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ModelComparison", () => {
  it("compares the model with the baseline and marks the better value as text too", async () => {
    serve({ "GET /api/v1/ml/models": { body: { items: [shadowModel, oldModel] } }, "GET /api/v1/ml/shadow": { body: shadow } });
    renderIt(false);

    const table = await screen.findByRole("table", { name: "Detector comparison" });
    const f1 = within(table).getByRole("row", { name: /^F1/ });
    expect(f1).toHaveTextContent("0.75");
    expect(f1).toHaveTextContent("0.87 (better)");
    const delay = within(table).getByRole("row", { name: /Median detection delay/ });
    expect(delay).toHaveTextContent("45 s (better)");
    expect(screen.getByRole("status")).toHaveTextContent("Meets the promotion rule: beats or complements the baseline");
    expect(screen.getByText(/checkout-http-500, checkout-latency/)).toBeInTheDocument();
  });

  it("shows shadow predictions next to the rule and incidents", async () => {
    serve({ "GET /api/v1/ml/models": { body: { items: [shadowModel] } }, "GET /api/v1/ml/shadow": { body: shadow } });
    renderIt(false);

    const table = await screen.findByRole("table", { name: "Shadow predictions by service" });
    expect(within(table).getByRole("row", { name: /Checkout/ })).toHaveTextContent("5760182");
  });

  it("lets administrators roll back to an earlier version", async () => {
    const user = userEvent.setup();
    const fetchMock = serve({
      "GET /api/v1/ml/models": { body: { items: [shadowModel, oldModel] } },
      "GET /api/v1/ml/shadow": { body: shadow },
      "POST /api/v1/ml/models/m-1/promote": { body: { ...oldModel, status: "shadow" } },
    });
    renderIt(true);

    await user.click(await screen.findByRole("button", { name: "Roll back to this version" }));

    expect(fetchMock.mock.calls.some(([r]) => r.method === "POST" && r.url.endsWith("/api/v1/ml/models/m-1/promote"))).toBe(true);
    expect(await screen.findByText("isolation-forest v1 now runs in shadow mode")).toBeInTheDocument();
  });

  it("offers no promotion to other roles", async () => {
    serve({ "GET /api/v1/ml/models": { body: { items: [shadowModel, oldModel] } }, "GET /api/v1/ml/shadow": { body: shadow } });
    renderIt(false);

    await screen.findByRole("table", { name: "Detector comparison" });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("explains how to get a first model", async () => {
    serve({ "GET /api/v1/ml/models": { body: { items: [] } }, "GET /api/v1/ml/shadow": { body: { ...shadow, model: null, services: [] } } });
    renderIt(true);

    expect(await screen.findByText("No model registered yet")).toBeInTheDocument();
  });
});
