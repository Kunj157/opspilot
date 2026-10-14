import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SidebarNav } from "./sidebar-nav";

vi.mock("next/navigation", () => ({ usePathname: () => "/incidents" }));

afterEach(() => vi.unstubAllGlobals());

function renderNav(
  items = [
    { href: "/", label: "Command center", icon: "overview" as const },
    { href: "/incidents", label: "Incidents", icon: "incidents" as const },
  ],
) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SidebarNav items={items} />
    </QueryClientProvider>,
  );
}

describe("SidebarNav", () => {
  it("marks the current section and shows the open incident count beside Incidents", async () => {
    const metrics = { active_by_severity: { critical: 2, high: 1, medium: 0, low: 4 } };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(metrics), { headers: { "Content-Type": "application/json" } })),
    );
    renderNav();

    const incidents = screen.getByRole("link", { name: "Incidents" });
    expect(incidents).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(incidents).toHaveTextContent("7"));
    // The badge is decorative, so the link's accessible name stays "Incidents".
    expect(screen.getByRole("link", { name: "Incidents" })).toBe(incidents);
  });

  it("does not ask for the count without the incidents section", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderNav([{ href: "/", label: "Command center", icon: "overview" }]);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
