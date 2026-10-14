import type { components } from "@opspilot/api-client/schema";

export type Topology = components["schemas"]["Topology"];
export type TopologyNode = Topology["nodes"][number];

export const COLUMN_WIDTH = 220;
export const ROW_HEIGHT = 96;
export const PADDING = 56;
/** Room for a centred label under the outermost nodes. */
export const PADDING_X = 100;
/** Longer layers wrap into extra columns so the map keeps a usable aspect ratio. */
export const MAX_ROWS = 5;

export type Position = { column: number; row: number; x: number; y: number };

/** A dependency on this service is failing: it is critical or has an open incident. */
export function isFailing(node: TopologyNode): boolean {
  return node.health_status === "critical" || node.active_incidents > 0;
}

const byName = (nodes: Map<string, TopologyNode>) => (a: string, b: string) =>
  nodes.get(a)!.name.localeCompare(nodes.get(b)!.name) || a.localeCompare(b);

/**
 * Layered layout: each service sits one column right of its furthest caller,
 * so calls read left to right. Cycles are cut by capping depth at the node count.
 */
export function layout(topology: Topology): {
  positions: Map<string, Position>;
  order: string[];
  width: number;
  height: number;
} {
  const nodes = new Map(topology.nodes.map((n) => [n.id, n]));
  const edges = topology.edges.filter((e) => nodes.has(e.source_id) && nodes.has(e.target_id));
  const depth = new Map(topology.nodes.map((n) => [n.id, 0]));
  for (let pass = 0; pass < nodes.size; pass++) {
    let changed = false;
    for (const { source_id, target_id } of edges) {
      const next = Math.min(depth.get(source_id)! + 1, nodes.size - 1);
      if (next > depth.get(target_id)!) {
        depth.set(target_id, next);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const layers: string[][] = [];
  for (const [id, d] of depth) (layers[d] ??= []).push(id);
  const filled = layers.filter(Boolean).flatMap((ids) => {
    ids.sort(byName(nodes));
    return Array.from({ length: Math.ceil(ids.length / MAX_ROWS) }, (_, i) =>
      ids.slice(i * MAX_ROWS, (i + 1) * MAX_ROWS),
    );
  });
  const tallest = Math.max(0, ...filled.map((c) => c.length));

  const positions = new Map<string, Position>();
  filled.forEach((ids, column) => {
    const offset = ((tallest - ids.length) * ROW_HEIGHT) / 2;
    ids.forEach((id, row) => {
      positions.set(id, {
        column,
        row,
        x: PADDING_X + column * COLUMN_WIDTH,
        y: PADDING + offset + row * ROW_HEIGHT,
      });
    });
  });

  return {
    positions,
    order: filled.flat(),
    width: PADDING_X * 2 + Math.max(0, filled.length - 1) * COLUMN_WIDTH,
    height: PADDING * 2 + Math.max(0, tallest - 1) * ROW_HEIGHT,
  };
}

/** Services a service calls, and services that call it, sorted by name. */
export function connections(topology: Topology, id: string): { dependencies: string[]; dependents: string[] } {
  const nodes = new Map(topology.nodes.map((n) => [n.id, n]));
  const sort = byName(nodes);
  return {
    dependencies: topology.edges
      .filter((e) => e.source_id === id)
      .map((e) => e.target_id)
      .sort(sort),
    dependents: topology.edges
      .filter((e) => e.target_id === id)
      .map((e) => e.source_id)
      .sort(sort),
  };
}
