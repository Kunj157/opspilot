import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SystemStatus } from "./system-status";

type Check = { status: "ok" | "fail"; detail: string | null };

function readiness(checks: Record<string, Check>, httpStatus = 200) {
  const ready = Object.values(checks).every((c) => c.status === "ok");
  return new Response(JSON.stringify({ status: ready ? "ready" : "not_ready", checks }), {
    status: httpStatus,
    headers: { "Content-Type": "application/json" },
  });
}

const ok: Check = { status: "ok", detail: null };

function renderStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SystemStatus />
    </QueryClientProvider>,
  );
}

function row(name: string) {
  return within(screen.getByRole("listitem", { name }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SystemStatus", () => {
  it("shows a checking state before the first response", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );

    renderStatus();

    expect(screen.getByRole("status")).toHaveTextContent(/checking/i);
  });

  it("reports all systems operational when the API is ready", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => readiness({ config: ok, database: ok, redis: ok })),
    );

    renderStatus();

    expect(await screen.findByText("All systems operational")).toBeInTheDocument();
    for (const name of ["API", "Configuration", "Database", "Redis"]) {
      expect(row(name).getByText("Operational")).toBeInTheDocument();
    }
  });

  it("reports degraded and names the failing dependency on 503", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => readiness({ config: ok, database: ok, redis: { status: "fail", detail: "unavailable" } }, 503)),
    );

    renderStatus();

    expect(await screen.findByText("Degraded")).toBeInTheDocument();
    expect(row("Redis").getByText("Unavailable")).toBeInTheDocument();
    expect(row("Database").getByText("Operational")).toBeInTheDocument();
    expect(row("API").getByText("Operational")).toBeInTheDocument();
  });

  it("distinguishes a timed-out dependency", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => readiness({ config: ok, database: { status: "fail", detail: "timeout" }, redis: ok }, 503)),
    );

    renderStatus();

    expect(await row("Database").findByText("Timed out")).toBeInTheDocument();
  });

  it("shows missing configuration", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => readiness({ config: { status: "fail", detail: "missing: REDIS_URL" }, database: ok }, 503)),
    );

    renderStatus();

    expect(await row("Configuration").findByText("Misconfigured")).toBeInTheDocument();
  });

  it("reports the API as unreachable when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    renderStatus();

    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
    expect(row("API").getByText("Unreachable")).toBeInTheDocument();
  });

  it("treats an unexpected status as unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("bad gateway", { status: 502 })),
    );

    renderStatus();

    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
  });

  it("never relies on colour alone: every row has a text status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => readiness({ config: ok, database: ok, redis: ok })),
    );

    renderStatus();

    await screen.findByText("All systems operational");
    for (const item of screen.getAllByRole("listitem")) {
      expect(within(item).getByTestId("status-label").textContent).not.toBe("");
    }
  });
});
