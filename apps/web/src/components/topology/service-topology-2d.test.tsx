import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { Topology } from "./model";
import { ServiceTopology2D } from "./service-topology-2d";

const topology: Topology = {
  nodes: [
    { id: "g", name: "Gateway", slug: "gateway", health_status: "healthy", active_incidents: 0, investigating: false },
    {
      id: "c",
      name: "Checkout",
      slug: "checkout",
      health_status: "degraded",
      active_incidents: 0,
      investigating: false,
    },
    { id: "p", name: "Payment", slug: "payment", health_status: "critical", active_incidents: 2, investigating: true },
  ],
  edges: [
    { source_id: "g", target_id: "c" },
    { source_id: "c", target_id: "p" },
  ],
};

function Harness({ onOpen = vi.fn() }: { onOpen?: (id: string) => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  return <ServiceTopology2D topology={topology} selectedId={selected} onSelect={setSelected} onOpen={onOpen} />;
}

const map = () => screen.getByRole("group", { name: "Service map" });
const node = (name: RegExp) => within(map()).getByRole("button", { name });

describe("ServiceTopology2D", () => {
  it("labels every service with its status, never colour alone", () => {
    render(<Harness />);

    expect(node(/^Gateway, healthy/)).toBeInTheDocument();
    expect(node(/^Checkout, degraded/)).toBeInTheDocument();
    expect(node(/^Payment, critical, 2 active incidents, under investigation/)).toBeInTheDocument();
  });

  it("is one tab stop; arrows move between services and select them", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.tab();
    expect(node(/^Gateway/)).toHaveFocus();
    expect(node(/^Gateway/)).toHaveAttribute("aria-pressed", "true");

    await user.keyboard("{ArrowRight}");
    expect(node(/^Checkout/)).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(node(/^Payment/)).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(node(/^Payment/)).toHaveFocus();
    await user.keyboard("{ArrowUp}{ArrowLeft}");
    expect(node(/^Gateway/)).toHaveFocus();

    expect(
      within(map())
        .getAllByRole("button")
        .filter((b) => b.tabIndex === 0),
    ).toHaveLength(1);
  });

  it("highlights the selected service's dependencies", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(node(/^Checkout/));

    const highlighted = map().querySelectorAll('[data-highlighted="true"]');
    expect([...highlighted].map((e) => e.getAttribute("data-edge"))).toEqual(["g→c", "c→p"]);
    expect(map().querySelector('[data-edge="c→p"]')).toHaveAttribute("data-failing", "true");
  });

  it("opens the focused service with Enter", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<Harness onOpen={onOpen} />);

    await user.click(node(/^Payment/));
    await user.keyboard("{Enter}");

    expect(onOpen).toHaveBeenCalledWith("p");
  });
});
