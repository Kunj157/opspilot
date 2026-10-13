import { isFailing, layout, PADDING, PADDING_X, type Topology, type TopologyNode } from "./model";

/** Layout pixels per scene unit. */
const SCALE = 1 / 70;

export type Shape = "sphere" | "cone" | "box" | "octahedron";
export type Vec3 = [number, number, number];

export type SceneNode = { id: string; node: TopologyNode; position: Vec3; shape: Shape };
export type SceneEdge = { id: string; sourceId: string; targetId: string; from: Vec3; to: Vec3; failing: boolean };

/** Same shapes as the 2D map and HealthBadge glyphs: ● ▲ ■ ○. */
const SHAPES: Record<TopologyNode["health_status"], Shape> = {
  healthy: "sphere",
  degraded: "cone",
  critical: "box",
  unknown: "octahedron",
};

/** The 2D layout, centred on the origin, with alternate columns set back for depth. */
export function toScene(topology: Topology): {
  nodes: SceneNode[];
  edges: SceneEdge[];
  /** Camera distance that fits the whole map in a 45° view at a wide aspect ratio. */
  distance: number;
} {
  const { positions, width, height } = layout(topology);
  const nodes = topology.nodes.flatMap((node) => {
    const p = positions.get(node.id);
    if (!p) return [];
    const position: Vec3 = [(p.x - width / 2) * SCALE, (height / 2 - p.y) * SCALE, p.column % 2 ? -0.8 : 0];
    return [{ id: node.id, node, position, shape: SHAPES[node.health_status] }];
  });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges = topology.edges.flatMap(({ source_id, target_id }) => {
    const source = byId.get(source_id);
    const target = byId.get(target_id);
    if (!source || !target) return [];
    return [
      {
        id: `${source_id}→${target_id}`,
        sourceId: source_id,
        targetId: target_id,
        from: source.position,
        to: target.position,
        failing: isFailing(target.node),
      },
    ];
  });
  const fit = Math.max(((width - 2 * PADDING_X) * SCALE) / 1.3, ((height - 2 * PADDING) * SCALE) / 0.7);
  return { nodes, edges, distance: Math.max(5, fit + 2) };
}

/** Whether this browser can create a WebGL context at all. */
export function canUseWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}
