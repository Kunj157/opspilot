"use client";

import { type KeyboardEvent, useRef } from "react";

import { isFailing, layout, type Topology, type TopologyNode } from "./model";

const NODE_RADIUS = 18;
const LABEL_CHARS = 24;

const shorten = (name: string) => (name.length > LABEL_CHARS ? `${name.slice(0, LABEL_CHARS - 1)}…` : name);

const HEALTH_LABEL: Record<TopologyNode["health_status"], string> = {
  healthy: "healthy",
  degraded: "degraded",
  critical: "critical",
  unknown: "health unknown",
};

const HEALTH_CLASS: Record<TopologyNode["health_status"], string> = {
  healthy: "fill-healthy",
  degraded: "fill-degraded",
  critical: "fill-critical",
  unknown: "fill-fg-muted",
};

export function describeNode(node: TopologyNode): string {
  const parts = [node.name, HEALTH_LABEL[node.health_status]];
  if (node.active_incidents > 0) {
    parts.push(`${node.active_incidents} active incident${node.active_incidents === 1 ? "" : "s"}`);
  }
  if (node.investigating) parts.push("under investigation");
  return parts.join(", ");
}

/** Status shape, so colour is never the only signal (matches HealthBadge glyphs). */
function Shape({ node }: { node: TopologyNode }) {
  const r = NODE_RADIUS * 0.55;
  const className = HEALTH_CLASS[node.health_status];
  switch (node.health_status) {
    case "degraded":
      return <path d={`M0 ${-r * 1.15} L${r} ${r * 0.75} L${-r} ${r * 0.75}Z`} className={className} />;
    case "critical":
      return <rect x={-r * 0.8} y={-r * 0.8} width={r * 1.6} height={r * 1.6} rx={2} className={className} />;
    case "unknown":
      return <circle r={r * 0.8} className="fill-none stroke-fg-muted" strokeWidth={2} />;
    default:
      return <circle r={r * 0.8} className={className} />;
  }
}

/** Accessible SVG service map: the fallback for, and equal of, the 3D view. */
export function ServiceTopology2D({
  topology,
  selectedId,
  onSelect,
  onOpen,
}: {
  topology: Topology;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
}) {
  const { positions, order, width, height } = layout(topology);
  const nodes = new Map(topology.nodes.map((n) => [n.id, n]));
  const refs = useRef(new Map<string, SVGGElement>());
  const focusable = selectedId && positions.has(selectedId) ? selectedId : order[0];

  function move(id: string, step: number) {
    const next = order[Math.min(order.length - 1, Math.max(0, order.indexOf(id) + step))];
    onSelect(next);
    refs.current.get(next)?.focus();
  }

  function onKeyDown(event: KeyboardEvent, id: string) {
    const steps: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    if (event.key in steps) {
      event.preventDefault();
      move(id, steps[event.key]);
    } else if (event.key === "Enter") {
      event.preventDefault();
      onOpen(id);
    } else if (event.key === " ") {
      event.preventDefault();
      onSelect(id);
    }
  }

  return (
    <svg
      role="group"
      aria-label="Service map"
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      // Natural size: the surrounding panel scrolls rather than shrinking labels.
      className="mx-auto block max-w-none"
    >
      <defs>
        <marker id="topology-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 8 4 0 8Z" className="fill-border-strong" />
        </marker>
      </defs>
      {topology.edges.map(({ source_id, target_id }) => {
        const from = positions.get(source_id);
        const to = positions.get(target_id);
        const target = nodes.get(target_id);
        if (!from || !to || !target) return null;
        const highlighted = selectedId === source_id || selectedId === target_id;
        const failing = isFailing(target);
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const length = Math.hypot(dx, dy) || 1;
        const trim = NODE_RADIUS + 4;
        return (
          <line
            key={`${source_id}→${target_id}`}
            data-edge={`${source_id}→${target_id}`}
            data-highlighted={highlighted}
            data-failing={failing}
            x1={from.x + (dx / length) * trim}
            y1={from.y + (dy / length) * trim}
            x2={to.x - (dx / length) * trim}
            y2={to.y - (dy / length) * trim}
            markerEnd="url(#topology-arrow)"
            strokeWidth={highlighted ? 2 : 1.25}
            className={`transition-opacity duration-base ${failing ? "stroke-critical" : "stroke-border-strong"} ${
              selectedId && !highlighted ? "opacity-30" : "opacity-100"
            }`}
          />
        );
      })}
      {order.map((id) => {
        const node = nodes.get(id)!;
        const { x, y } = positions.get(id)!;
        const selected = id === selectedId;
        return (
          <g
            key={id}
            ref={(el) => {
              if (el) refs.current.set(id, el);
              else refs.current.delete(id);
            }}
            role="button"
            aria-label={describeNode(node)}
            aria-pressed={selected}
            aria-keyshortcuts="Enter"
            tabIndex={id === focusable ? 0 : -1}
            transform={`translate(${x} ${y})`}
            onClick={() => onSelect(id)}
            onFocus={() => onSelect(id)}
            onDoubleClick={() => onOpen(id)}
            onKeyDown={(e) => onKeyDown(e, id)}
            className="group cursor-pointer outline-none"
          >
            <circle
              r={NODE_RADIUS}
              className={`fill-surface-3 transition-colors duration-base ${
                selected ? "stroke-accent" : "stroke-border-strong group-hover:stroke-fg-muted"
              } group-focus-visible:stroke-accent`}
              strokeWidth={selected ? 2.5 : 1.5}
            />
            {node.investigating && (
              <circle r={NODE_RADIUS + 6} className="animate-pulse fill-none stroke-accent" strokeWidth={1.5} />
            )}
            <Shape node={node} />
            <text y={NODE_RADIUS + 18} textAnchor="middle" className="fill-fg text-[12px] font-medium">
              {shorten(node.name)}
            </text>
            {node.active_incidents > 0 && (
              <text y={NODE_RADIUS + 33} textAnchor="middle" className="fill-fg-secondary font-mono text-[10px]">
                {node.active_incidents} open
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
