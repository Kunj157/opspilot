import type { components } from "@opspilot/api-client/schema";

export type Severity = components["schemas"]["Severity"];
export type IncidentStatus = components["schemas"]["IncidentStatus"];

const SEVERITY: Record<Severity, { label: string; className: string; bars: number }> = {
  critical: { label: "Critical", className: "text-critical border-critical/40", bars: 4 },
  high: { label: "High", className: "text-critical border-critical/25", bars: 3 },
  medium: { label: "Medium", className: "text-degraded border-degraded/30", bars: 2 },
  low: { label: "Low", className: "text-fg-secondary border-border-strong", bars: 1 },
};

/** Severity as text plus a bar glyph, so colour is never the only signal. */
export function SeverityBadge({ severity }: { severity: Severity }) {
  const { label, className, bars } = SEVERITY[severity];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}
    >
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
        {[0, 1, 2, 3].map((i) => (
          <rect
            key={i}
            x={i * 2.6}
            y={7 - i * 2}
            width="1.8"
            height={3 + i * 2}
            rx="0.5"
            fill="currentColor"
            opacity={i < bars ? 1 : 0.25}
          />
        ))}
      </svg>
      {label}
    </span>
  );
}

const STATUS_LABEL: Record<IncidentStatus, string> = {
  DETECTED: "Detected",
  INVESTIGATING: "Investigating",
  AWAITING_APPROVAL: "Awaiting approval",
  REMEDIATING: "Remediating",
  VERIFYING: "Verifying",
  MONITORING: "Monitoring",
  RESOLVED: "Resolved",
  REJECTED: "Rejected",
};

export function statusLabel(status: IncidentStatus): string {
  return STATUS_LABEL[status];
}

/** Investigation in progress uses Iris, the colour of OpsPilot acting (plan §16.1). */
export function StatusBadge({ status }: { status: IncidentStatus }) {
  const tone =
    status === "RESOLVED"
      ? "text-healthy"
      : status === "INVESTIGATING" || status === "REMEDIATING" || status === "VERIFYING"
        ? "text-accent"
        : status === "AWAITING_APPROVAL"
          ? "text-degraded"
          : "text-fg-secondary";
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${tone}`}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {STATUS_LABEL[status]}
    </span>
  );
}
