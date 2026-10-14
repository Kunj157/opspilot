import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Topology } from "./model";
import { TopologyPanel } from "./topology-panel";

const push = vi.fn();
const navigation = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

function serve(topology: Topology) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(topology), { headers: { "Content-Type": "application/json" } })),
  );
}

const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderIt(queryClient = client()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <TopologyPanel />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  push.mockReset();
  navigation.search = "";
});

const shop: Topology = {
  nodes: [
    {
      id: "c",
      name: "Checkout",
      slug: "checkout",
      health_status: "healthy",
      active_incidents: 0,
      investigating: false,
    },
    { id: "p", name: "Payment", slug: "payment", health_status: "critical", active_incidents: 1, investigating: false },
  ],
  edges: [{ source_id: "c", target_id: "p" }],
};

describe("TopologyPanel", () => {
  it("shows an empty state when there are no services", async () => {
    serve({ nodes: [], edges: [] });
    renderIt();

    expect(await screen.findByText(/no services to map yet/i)).toBeInTheDocument();
  });

  it("describes the selected service and links to it", async () => {
    const user = userEvent.setup();
    serve(shop);
    renderIt();

    await user.click(await screen.findByRole("button", { name: /^Checkout/ }));

    const details = screen.getByRole("region", { name: "Selected service" });
    expect(within(details).getByRole("heading", { name: "Checkout" })).toBeInTheDocument();
    expect(within(details).getByRole("list", { name: "Calls" })).toHaveTextContent("Payment");
    expect(within(details).getByRole("link", { name: "Open Checkout" })).toHaveAttribute("href", "/services/c");
  });

  it("selects the service named in ?focus= and brings the map into view", async () => {
    serve(shop);
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    navigation.search = "focus=c";
    renderIt();

    const details = await screen.findByRole("region", { name: "Selected service" });
    expect(within(details).getByRole("heading", { name: "Checkout" })).toBeInTheDocument();
    expect(scroll).toHaveBeenCalled();
  });

  it("opens a service from the keyboard", async () => {
    const user = userEvent.setup();
    serve(shop);
    renderIt();
    const map = await screen.findByRole("group", { name: "Service map" });

    await user.click(within(map).getByRole("button", { name: /^Checkout/ }));
    await user.keyboard("{ArrowRight}{Enter}");

    expect(push).toHaveBeenCalledWith("/services/p");
  });

  it("offers a list of services for small screens", async () => {
    serve(shop);
    renderIt();

    const list = await screen.findByRole("list", { name: "Services by dependency" });
    expect(within(list).getByRole("link", { name: /Payment/ })).toHaveAttribute("href", "/services/p");
    expect(within(list).getByText("Calls Payment")).toBeInTheDocument();
  });
});
