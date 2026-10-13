import type { components } from "@opspilot/api-client/schema";

type Health = components["schemas"]["HealthStatus"];

const HEALTH: Record<Health, { label: string; className: string; glyph: string }> = {
  healthy: { label: "Healthy", className: "text-healthy", glyph: "●" },
  degraded: { label: "Degraded", className: "text-degraded", glyph: "▲" },
  critical: { label: "Critical", className: "text-critical", glyph: "■" },
  unknown: { label: "Unknown", className: "text-fg-muted", glyph: "○" },
};

/** Health as text plus a distinct glyph per state, never colour alone. */
export function HealthBadge({ health }: { health: Health }) {
  const { label, className, glyph } = HEALTH[health];
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${className}`}>
      <span aria-hidden className="text-[0.7em]">
        {glyph}
      </span>
      {label}
    </span>
  );
}
