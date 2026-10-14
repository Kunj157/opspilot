import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import CommandPalette from "./command-palette";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const RESPONSES: Record<string, unknown> = {
  "/api/v1/me": { permissions: ["view_incidents", "view_services", "manage_incidents"] },
  "/api/v1/incidents": { items: [{ id: "i1", title: "Checkout latency spike", severity: "critical", status: "DETECTED" }] },
  "/api/v1/services": { items: [{ id: "s1", name: "Payments", slug: "payments", health_status: "degraded" }] },
};

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.open = false;
  };
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      return new Response(JSON.stringify(RESPONSES[path] ?? {}), { headers: { "Content-Type": "application/json" } });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  push.mockReset();
});

function renderPalette(onClose = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CommandPalette open onClose={onClose} />
    </QueryClientProvider>,
  );
  return onClose;
}

describe("CommandPalette", () => {
  it("offers navigation, actions, incidents, and services the user may see", async () => {
    renderPalette();
    const results = screen.getByRole("listbox", { name: "Results" });
    await waitFor(() => expect(results).toHaveTextContent("Checkout latency spike"));
    expect(screen.getByRole("group", { name: "Go to" })).toHaveTextContent("Incidents");
    expect(screen.getByRole("group", { name: "Actions" })).toHaveTextContent("New incident");
    expect(screen.getByRole("group", { name: "Services" })).toHaveTextContent("Payments");
    // The viewer-only audit log needs view_audit_logs, which this user lacks.
    expect(results).not.toHaveTextContent("Audit log");
  });

  it("filters as you type and opens the highlighted result with Enter", async () => {
    const user = userEvent.setup();
    const onClose = renderPalette();
    const input = screen.getByRole("combobox", { name: "Search commands" });
    await waitFor(() => expect(screen.getByRole("listbox")).toHaveTextContent("Payments"));

    await user.type(input, "paym");
    const options = screen.getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["Paymentsdegraded", "Show Payments on the map"]);
    expect(input).toHaveAttribute("aria-activedescendant", options[0].id);
    await user.keyboard("{Enter}");

    expect(onClose).toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith("/services/s1");
  });

  it("moves the selection with the arrow keys and wraps", async () => {
    const user = userEvent.setup();
    renderPalette();
    const input = screen.getByRole("combobox", { name: "Search commands" });
    await user.type(input, "status");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowUp}");
    const options = screen.getAllByRole("option");
    expect(options[options.length - 1]).toHaveAttribute("aria-selected", "true");
  });

  it("says so when nothing matches", async () => {
    const user = userEvent.setup();
    renderPalette();
    await user.type(screen.getByRole("combobox", { name: "Search commands" }), "zzzz");
    expect(screen.getByText(/No matches/)).toBeInTheDocument();
  });
});
