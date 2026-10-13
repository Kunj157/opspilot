import { afterEach, describe, expect, it, vi } from "vitest";

import type { Topology } from "./model";
import { canUseWebGL, toScene } from "./scene";

const topology: Topology = {
  nodes: [
    { id: "a", name: "A", slug: "a", health_status: "healthy", active_incidents: 0, investigating: false },
    { id: "b", name: "B", slug: "b", health_status: "critical", active_incidents: 1, investigating: true },
    { id: "c", name: "C", slug: "c", health_status: "degraded", active_incidents: 0, investigating: false },
  ],
  edges: [
    { source_id: "a", target_id: "b" },
    { source_id: "a", target_id: "c" },
  ],
};

describe("toScene", () => {
  it("centres the layout on the origin", () => {
    const { nodes } = toScene(topology);
    const xs = nodes.map((n) => n.position[0]);
    const ys = nodes.map((n) => n.position[1]);

    expect(Math.min(...xs) + Math.max(...xs)).toBeCloseTo(0);
    expect(Math.min(...ys) + Math.max(...ys)).toBeCloseTo(0);
  });

  it("keeps callers to the left and gives each status its own shape", () => {
    const { nodes } = toScene(topology);
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

    expect(byId.a.position[0]).toBeLessThan(byId.b.position[0]);
    expect([byId.a.shape, byId.b.shape, byId.c.shape]).toEqual(["sphere", "box", "cone"]);
  });

  it("connects edges between node positions and marks failing ones", () => {
    const { nodes, edges } = toScene(topology);
    const a = nodes.find((n) => n.id === "a")!;

    expect(edges).toHaveLength(2);
    expect(edges[0].from).toEqual(a.position);
    expect(edges.map((e) => e.failing)).toEqual([true, false]);
  });

  it("frames the camera further away for wider maps", () => {
    const small = toScene({ nodes: topology.nodes.slice(0, 1), edges: [] });
    const many = Array.from({ length: 30 }, (_, i) => ({ ...topology.nodes[0], id: `n${i}`, name: `N${i}` }));

    expect(toScene({ nodes: many, edges: [] }).distance).toBeGreaterThan(small.distance);
  });
});

describe("canUseWebGL", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is false when no WebGL context can be created", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);

    expect(canUseWebGL()).toBe(false);
  });

  it("is false when creating a context throws", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(canUseWebGL()).toBe(false);
  });

  it("is true when a context exists", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as RenderingContext);

    expect(canUseWebGL()).toBe(true);
  });
});
