"use client";

import { createApiClient } from "@opspilot/api-client";
import { useQuery } from "@tanstack/react-query";

import { type IncidentStatus, SeverityBadge, StatusBadge } from "./incidents/badges";

const ACTIVE: IncidentStatus[] = [
  "DETECTED",
  "INVESTIGATING",
  "AWAITING_APPROVAL",
  "REMEDIATING",
  "VERIFYING",
  "MONITORING",
  "REJECTED",
];

async function loadSummary(signal: AbortSignal) {
  const api = createApiClient(window.location.origin);
  const [incidents, services] = await Promise.all([
    api.GET("/api/v1/incidents", { params: { query: { status: ACTIVE, limit: 200 } }, signal }),
    api.GET("/api/v1/services", { signal }),
  ]);
  if (!incidents.data || !services.data) throw new Error("summary unavailable");
  return { incidents: incidents.data.items, services: services.data.items };
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div
      role="group"
      aria-label={label}
      className="rounded-card border border-border bg-surface-2 p-5 shadow-2 transition-transform duration-base hover:-translate-y-0.5 motion-reduce:hover:translate-y-0"
    >
      <p className="text-xs text-fg-secondary">{label}</p>
      <p className={`mt-2 font-mono text-3xl font-semibold tracking-tight ${tone ?? "text-fg"}`}>
        {value}
      </p>
    </div>
  );
}

const time = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function CommandCenter() {
  const summary = useQuery({
    queryKey: ["command-center"],
    queryFn: ({ signal }) => loadSummary(signal),
    refetchInterval: 30_000,
  });

  if (summary.isPending) {
    return (
      <div aria-hidden className="grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-card bg-surface-2" />
        ))}
      </div>
    );
  }
  if (summary.isError) {
    return (
      <p role="alert" className="rounded-card border border-border bg-surface-2 p-5 text-sm text-critical">
        The command center summary could not be loaded.
      </p>
    );
  }

  const { incidents, services } = summary.data;
  const critical = incidents.filter((i) => i.severity === "critical").length;
  const healthy = services.filter((s) => s.health_status === "healthy").length;

  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Active incidents" value={String(incidents.length)} />
        <Stat
          label="Critical incidents"
          value={String(critical)}
          tone={critical > 0 ? "text-critical" : undefined}
        />
        <Stat
          label="Healthy services"
          value={services.length ? `${healthy} of ${services.length}` : "—"}
          tone={services.length && healthy === services.length ? "text-healthy" : undefined}
        />
      </div>

      <section aria-labelledby="recent-heading" className="rounded-card border border-border bg-surface-2 shadow-3">
        <h2 id="recent-heading" className="border-b border-border px-5 py-4 text-sm font-medium text-fg-secondary">
          Recent active incidents
        </h2>
        {incidents.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-fg-muted">No active incidents.</p>
        ) : (
          <ul aria-label="Recent incidents" className="divide-y divide-border">
            {incidents.slice(0, 5).map((incident) => (
              <li key={incident.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5">
                <SeverityBadge severity={incident.severity} />
                <span className="min-w-0 flex-1 truncate text-sm">{incident.title}</span>
                <StatusBadge status={incident.status} />
                <time dateTime={incident.started_at} className="font-mono text-xs text-fg-muted">
                  {time.format(new Date(incident.started_at))}
                </time>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
