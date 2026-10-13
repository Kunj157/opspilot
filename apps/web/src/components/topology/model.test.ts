import { describe, expect, it } from "vitest";

import { connections, isFailing, layout, type Topology } from "./model";

function node(id: string, extra: Partial<Topology["nodes"][number]> = {}): Topology["nodes"][number] {
  return {
    id,
    name: id[0].toUpperCase() + id.slice(1),
    slug: id,
    health_status: "healthy",
    active_incidents: 0,
    investigating: false,
    ...extra,
  };
}

const shop: Topology = {
  nodes: [node("gateway"), node("checkout"), node("payment"), node("inventory"), node("audit")],
  edges: [
    { source_id: "gateway", target_id: "checkout" },
    { source_id: "checkout", target_id: "payment" },
    { source_id: "checkout", target_id: "inventory" },
    { source_id: "gateway", target_id: "inventory" },
  ],
};

describe("layout", () => {
  it("places callers in earlier columns than the services they call", () => {
    const { positions } = layout(shop);

    expect(positions.get("gateway")!.column).toBe(0);
    expect(positions.get("checkout")!.column).toBe(1);
    // Longest path wins: gateway → checkout → inventory.
    expect(positions.get("inventory")!.column).toBe(2);
    expect(positions.get("payment")!.column).toBe(2);
    expect(positions.get("audit")!.column).toBe(0);
  });

  it("orders services in a column by name and returns reading order", () => {
    const { order } = layout(shop);

    expect(order).toEqual(["audit", "gateway", "checkout", "inventory", "payment"]);
  });

  it("is deterministic and survives cycles", () => {
    const cyclic: Topology = {
      nodes: [node("a"), node("b"), node("c")],
      edges: [
        { source_id: "a", target_id: "b" },
        { source_id: "b", target_id: "c" },
        { source_id: "c", target_id: "a" },
      ],
    };

    const first = layout(cyclic);
    expect(layout(cyclic)).toEqual(first);
    expect(first.order).toHaveLength(3);
  });

  it("sizes the canvas to the widest column", () => {
    const { width, height } = layout(shop);

    expect(width).toBeGreaterThan(0);
    expect(height).toBeGreaterThan(0);
    expect(layout({ nodes: [], edges: [] }).order).toEqual([]);
  });
});

it("wraps a long layer into extra columns", () => {
  const many: Topology = {
    nodes: Array.from({ length: 12 }, (_, i) => node(`svc${String(i).padStart(2, "0")}`)),
    edges: [],
  };

  const { positions } = layout(many);

  expect(positions.get("svc04")!.column).toBe(0);
  expect(positions.get("svc05")!.column).toBe(1);
  expect(positions.get("svc11")!.column).toBe(2);
  expect(Math.max(...[...positions.values()].map((p) => p.row))).toBe(4);
});

describe("connections", () => {
  it("lists what a service calls and what calls it", () => {
    expect(connections(shop, "checkout")).toEqual({
      dependencies: ["inventory", "payment"],
      dependents: ["gateway"],
    });
  });
});

describe("isFailing", () => {
  it("treats critical health or an active incident as failing", () => {
    expect(isFailing(node("x"))).toBe(false);
    expect(isFailing(node("x", { health_status: "critical" }))).toBe(true);
    expect(isFailing(node("x", { active_incidents: 1 }))).toBe(true);
  });
});
