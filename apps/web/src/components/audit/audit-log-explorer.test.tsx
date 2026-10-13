import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuditLogExplorer } from "./audit-log-explorer";

type Item = {
  id: string;
  actor_type: "user" | "agent" | "system";
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip_address: string | null;
  request_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

function item(n: number, overrides: Partial<Item> = {}): Item {
  return {
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    actor_type: "user",
    actor_id: `user-${n}`,
    action: "http.post",
    resource_type: "http_request",
    resource_id: `/api/v1/things/${n}`,
    ip_address: "203.0.113.7",
    request_id: `req-${n}`,
    metadata: {},
    created_at: new Date(Date.UTC(2026, 9, 13, 12, 0, n)).toISOString(),
    ...overrides,
  };
}

function page(items: Item[], next_cursor: string | null = null, status = 200) {
  return new Response(JSON.stringify({ items, next_cursor }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderExplorer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuditLogExplorer />
    </QueryClientProvider>,
  );
}

function requestedUrl(fetchMock: ReturnType<typeof vi.fn>, call = 0) {
  const input = fetchMock.mock.calls[call][0] as Request | string;
  return new URL(typeof input === "string" ? input : input.url);
}

afterEach(() => vi.unstubAllGlobals());

describe("AuditLogExplorer", () => {
  it("lists entries newest first with their key fields", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => page([item(2, { action: "user.provisioned", actor_type: "system", actor_id: "provisioning" }), item(1)])));

    renderExplorer();

    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("user.provisioned")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/system/i)).toBeInTheDocument();
    expect(within(rows[1]).getByText("/api/v1/things/1")).toBeInTheDocument();
    expect(within(rows[1]).getByText("req-1")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => page([])));

    renderExplorer();

    expect(await screen.findByText("No audit records match these filters.")).toBeInTheDocument();
  });

  it("shows a forbidden state on 403", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"detail":"Forbidden"}', { status: 403 })));

    renderExplorer();

    expect(await screen.findByText("You don't have access to the audit log.")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("boom", { status: 500 }))
      .mockResolvedValueOnce(page([item(1)]));
    vi.stubGlobal("fetch", fetchMock);

    renderExplorer();
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));

    expect(await screen.findAllByRole("listitem")).toHaveLength(1);
  });

  it("loads more pages until there are none left", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(page([item(3), item(2)], "cursor-1"))
      .mockResolvedValueOnce(page([item(1)], null));
    vi.stubGlobal("fetch", fetchMock);

    renderExplorer();
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));

    expect(await screen.findAllByRole("listitem")).toHaveLength(3);
    expect(requestedUrl(fetchMock, 1).searchParams.get("cursor")).toBe("cursor-1");
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("applies filters as query parameters", async () => {
    const fetchMock = vi.fn(async () => page([]));
    vi.stubGlobal("fetch", fetchMock);

    renderExplorer();
    await screen.findByText("No audit records match these filters.");
    await userEvent.type(screen.getByLabelText("Action"), "user.provisioned");
    await userEvent.type(screen.getByLabelText("Resource type"), "user");
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const url = requestedUrl(fetchMock, 1);
    expect(url.pathname).toBe("/api/v1/audit-logs");
    expect(url.searchParams.get("action")).toBe("user.provisioned");
    expect(url.searchParams.get("resource_type")).toBe("user");
  });
});
