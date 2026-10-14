import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CommandCenter } from "./command-center";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const METRICS = {
  window_days: 30,
  mtta_seconds: 6 * 60,
  mttr_seconds: null,
  acknowledged: 2,
  resolved: 0,
  active_by_severity: { critical: 1, high: 1, medium: 0, low: 1 },
  daily: [{ date: "2026-10-13", critical: 1, high: 1, medium: 0, low: 1 }],
};

class SilentEventSource {
  addEventListener() {}
  close() {}
}

function incident(n: number, severity: string, status = "DETECTED") {
  return {
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    title: `Incident ${n}`,
    description: null,
    severity,
    status,
    source: "manual",
    service_id: null,
    started_at: new Date(Date.UTC(2026, 9, 13, 12, n)).toISOString(),
    acknowledged_at: null,
    resolved_at: null,
    detection_score: null,
    assigned_user_id: null,
    version: 1,
    created_at: "2026-10-13T12:00:00Z",
    updated_at: "2026-10-13T12:00:00Z",
    allowed_transitions: [],
  };
}

function service(n: number, health: string) {
  return { id: `svc-${n}`, name: `Service ${n}`, slug: `s${n}`, health_status: health };
}

function respond(routes: Record<string, unknown>, status = 200) {
  return vi.fn(async (input: Request | string) => {
    const url = new URL(typeof input === "string" ? input : input.url);
    const defaults: Record<string, unknown> = {
      "/api/v1/topology": { nodes: [], edges: [] },
      "/api/v1/incident-metrics": METRICS,
    };
    const body = routes[url.pathname] ?? defaults[url.pathname];
    return new Response(JSON.stringify(body ?? {}), {
      status: body === undefined ? 404 : status,
      headers: { "Content-Type": "application/json" },
    });
  });
}

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CommandCenter />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("EventSource", SilentEventSource);
  // Numbers count up from zero; reduced motion shows the final values at once.
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("reduce"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});
afterEach(() => vi.unstubAllGlobals());

describe("CommandCenter", () => {
  it("summarises active incidents and service health", async () => {
    vi.stubGlobal(
      "fetch",
      respond({
        "/api/v1/incidents": {
          items: [incident(3, "critical"), incident(2, "high", "INVESTIGATING"), incident(1, "low")],
          next_cursor: null,
        },
        "/api/v1/services": {
          items: [service(1, "healthy"), service(2, "healthy"), service(3, "critical")],
        },
      }),
    );

    renderIt();

    const active = await screen.findByRole("group", { name: "Active incidents" });
    expect(within(active).getByText("3")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Critical incidents" })).getByText("1")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Healthy services" })).toHaveTextContent("2 of 3");
    expect(within(screen.getByRole("group", { name: "Mean time to acknowledge" })).getByText("6m")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Mean time to resolve" })).getByText("—")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /incidents started per day/i })).toBeInTheDocument();
    const recent = screen.getByRole("list", { name: "Recent incidents" });
    expect(within(recent).getAllByRole("listitem")).toHaveLength(3);
    expect(within(recent).getAllByRole("listitem")[0]).toHaveTextContent("Incident 3");
  });

  it("asks only for unresolved incidents", async () => {
    const fetchMock = respond({
      "/api/v1/incidents": { items: [], next_cursor: null },
      "/api/v1/services": { items: [] },
    });
    vi.stubGlobal("fetch", fetchMock);

    renderIt();
    await screen.findByText("No active incidents.");

    const incidentsCall = fetchMock.mock.calls
      .map(([input]) => new URL(typeof input === "string" ? input : input.url))
      .find((url) => url.pathname === "/api/v1/incidents");
    expect(incidentsCall?.searchParams.getAll("status")).not.toContain("RESOLVED");
    expect(incidentsCall?.searchParams.getAll("status")).toContain("DETECTED");
  });

  it("shows an error when the summary cannot load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("boom", { status: 500 })),
    );

    renderIt();

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
