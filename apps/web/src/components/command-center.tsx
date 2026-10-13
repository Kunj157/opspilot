"use client";

import { createApiClient } from "@opspilot/api-client";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { TOPOLOGY_KEY, TopologyPanel } from "@/components/topology/topology-panel";
import { Card } from "@/components/ui/card";
import { formatSeconds } from "@/lib/durations";

import { AlertStream } from "./command-center/alert-stream";
import { SeverityChart } from "./command-center/severity-chart";

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

const METRICS_WINDOW_DAYS = 30;
const CHART_DAYS = 14;

async function loadSummary(signal: AbortSignal) {
  const api = createApiClient(window.location.origin);
  const [incidents, services, metrics] = await Promise.all([
    api.GET("/api/v1/incidents", { params: { query: { status: ACTIVE, limit: 200 } }, signal }),
    api.GET("/api/v1/services", { signal }),
    api.GET("/api/v1/incident-metrics", { params: { query: { days: METRICS_WINDOW_DAYS } }, signal }),
  ]);
  if (!incidents.data || !services.data || !metrics.data) throw new Error("summary unavailable");
  return { incidents: incidents.data.items, services: services.data.items, metrics: metrics.data };
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <Card tilt role="group" aria-label={label} className="p-5">
      <p className="text-xs text-fg-secondary">{label}</p>
      <p className={`mt-2 font-mono text-3xl font-semibold tracking-tight ${tone ?? "text-fg"}`}>
        {value}
      </p>
    </Card>
  );
}

const time = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function CommandCenter() {
  const queryClient = useQueryClient();
  const summary = useQuery({
    queryKey: ["command-center"],
    queryFn: ({ signal }) => loadSummary(signal),
    refetchInterval: 30_000,
  });

  if (summary.isPending) {
    return (
      <div aria-hidden className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
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

  const { incidents, services, metrics } = summary.data;
  const critical = incidents.filter((i) => i.severity === "critical").length;
  const healthy = services.filter((s) => s.health_status === "healthy").length;

  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
        <Stat label="Mean time to acknowledge" value={formatSeconds(metrics.mtta_seconds)} />
        <Stat label="Mean time to resolve" value={formatSeconds(metrics.mttr_seconds)} />
        <Stat label={`Resolved in ${metrics.window_days} days`} value={String(metrics.resolved)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <Card as="section" aria-labelledby="severity-heading" className="p-5">
          <h2 id="severity-heading" className="mb-4 text-sm font-medium text-fg-secondary">
            Incidents by severity, last {CHART_DAYS} days
          </h2>
          <SeverityChart daily={metrics.daily.slice(-CHART_DAYS)} />
        </Card>
        <Card as="section" aria-label="Live alerts" className="overflow-hidden">
          <AlertStream
            onEvent={() => {
              void queryClient.invalidateQueries({ queryKey: ["command-center"] });
              void queryClient.invalidateQueries({ queryKey: TOPOLOGY_KEY });
            }}
          />
        </Card>
      </div>

      <TopologyPanel />

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
                <Link href={`/incidents/${incident.id}`} className="min-w-0 flex-1 truncate text-sm hover:text-accent">
                  {incident.title}
                </Link>
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
