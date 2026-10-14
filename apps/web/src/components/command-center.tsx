"use client";

import { createApiClient } from "@opspilot/api-client";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { AnimatedNumber } from "@/components/motion/animated-number";
import { GlowEffect } from "@/components/motion/glow-effect";
import { TOPOLOGY_KEY, TopologyPanel } from "@/components/topology/topology-panel";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
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

/** A tiny neutral trend line; decorative, the chart below carries the numbers. */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const max = Math.max(1, ...values);
  const step = 100 / (values.length - 1);
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${(28 - (v / max) * 24).toFixed(1)}`);
  return (
    <svg
      aria-hidden
      viewBox="0 0 100 30"
      preserveAspectRatio="none"
      className="absolute right-5 bottom-5 h-8 w-24 overflow-visible"
    >
      <polyline points={`0,30 ${points.join(" ")} 100,30`} className="fill-accent-subtle stroke-none" />
      <polyline
        points={points.join(" ")}
        fill="none"
        vectorEffect="non-scaling-stroke"
        className="stroke-chart-1"
        strokeWidth={1.5}
      />
    </svg>
  );
}

function Stat({
  label,
  value,
  format,
  suffix,
  tone,
  alert = false,
  trend,
}: {
  label: string;
  /** null renders "—". */
  value: number | null;
  format?: (n: number) => string;
  suffix?: string;
  tone?: string;
  /** Something needs attention now: a soft critical halo that breathes. */
  alert?: boolean;
  trend?: number[];
}) {
  return (
    <div className="relative">
      {alert && <GlowEffect tone="critical" breathing className="rounded-card" />}
      <Card tilt role="group" aria-label={label} className="relative h-full overflow-hidden p-5">
        <p className="flex items-center gap-2 text-xs text-fg-secondary">
          {alert && <span aria-hidden className="pulse-dot size-1.5 rounded-full bg-critical" />}
          {label}
        </p>
        <p className={`mt-2 font-mono text-3xl font-semibold tracking-tight ${tone ?? "text-fg"}`}>
          {value === null ? "—" : <AnimatedNumber value={value} from={0} format={format} />}
          {value !== null && suffix}
        </p>
        {trend && <Sparkline values={trend} />}
      </Card>
    </div>
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
          <div key={i} className="skeleton h-28 rounded-card" />
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
  const perDay = metrics.daily.slice(-CHART_DAYS).map((d) => d.critical + d.high + d.medium + d.low);

  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Stat label="Active incidents" value={incidents.length} trend={perDay} />
        <Stat
          label="Critical incidents"
          value={critical}
          tone={critical > 0 ? "text-critical" : undefined}
          alert={critical > 0}
        />
        <Stat
          label="Healthy services"
          value={services.length ? healthy : null}
          suffix={` of ${services.length}`}
          tone={services.length && healthy === services.length ? "text-healthy" : undefined}
        />
        <Stat label="Mean time to acknowledge" value={metrics.mtta_seconds} format={formatSeconds} />
        <Stat label="Mean time to resolve" value={metrics.mttr_seconds} format={formatSeconds} />
        <Stat label={`Resolved in ${metrics.window_days} days`} value={metrics.resolved} />
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

      <section aria-labelledby="recent-heading" className="surface-raised rounded-card border border-border">
        <h2 id="recent-heading" className="border-b border-border px-5 py-4 text-sm font-medium text-fg-secondary">
          Recent active incidents
        </h2>
        {incidents.length === 0 ? (
          <EmptyState
            tone="positive"
            title="No active incidents."
            description="Every service is quiet. New incidents appear here and in the live stream as they open."
          />
        ) : (
          <ul aria-label="Recent incidents" className="divide-y divide-border">
            {incidents.slice(0, 5).map((incident) => (
              <li
                key={incident.id}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5 transition-colors duration-(--duration-instant) hover:bg-surface-3/60"
              >
                <span className="relative inline-flex">
                  {incident.severity === "critical" && (
                    <span aria-hidden className="pulse-ring absolute inset-0 rounded-full" />
                  )}
                  <SeverityBadge severity={incident.severity} />
                </span>
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
