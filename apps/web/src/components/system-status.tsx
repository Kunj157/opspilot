"use client";

import { useQuery } from "@tanstack/react-query";

import { describeCheck, fetchReadiness, type ReadinessResult, type Tone } from "@/lib/readiness";

const REFRESH_MS = 10_000;

const CHECK_NAMES: Record<string, string> = {
  config: "Configuration",
  database: "Database",
  redis: "Redis",
};

type Row = { name: string; label: string; tone: Tone };

function rowsFor(result: ReadinessResult | undefined): Row[] {
  if (!result) {
    return ["API", ...Object.values(CHECK_NAMES)].map((name) => ({
      name,
      label: "Checking",
      tone: "unknown",
    }));
  }
  if (!result.reachable) {
    return [
      { name: "API", label: "Unreachable", tone: "critical" },
      ...Object.values(CHECK_NAMES).map((name) => ({
        name,
        label: "Unknown",
        tone: "unknown" as const,
      })),
    ];
  }
  const checks = Object.entries(result.readiness.checks).map(([key, check]) => ({
    name: CHECK_NAMES[key] ?? key,
    ...describeCheck(check),
  }));
  return [{ name: "API", label: "Operational", tone: "healthy" }, ...checks];
}

function summaryFor(result: ReadinessResult | undefined): { text: string; tone: Tone } {
  if (!result) return { text: "Checking systems…", tone: "unknown" };
  if (!result.reachable) return { text: "API unreachable", tone: "critical" };
  if (result.readiness.status === "ready") return { text: "All systems operational", tone: "healthy" };
  return { text: "Degraded", tone: "degraded" };
}

const toneText: Record<Tone, string> = {
  healthy: "text-healthy",
  degraded: "text-degraded",
  critical: "text-critical",
  unknown: "text-fg-muted",
};

function StatusIcon({ tone }: { tone: Tone }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 16 16",
    fill: "none",
    "aria-hidden": true,
    className: toneText[tone],
  } as const;
  switch (tone) {
    case "healthy":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
          <path
            d="M5 8.2 7 10.2 11 6"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "degraded":
      return (
        <svg {...common}>
          <path d="M8 1.8 14.6 13.5H1.4L8 1.8Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M8 6.5v3M8 11.6v.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      );
    case "critical":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
          <path d="m5.5 5.5 5 5m0-5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2.5 2.5" />
        </svg>
      );
  }
}

export function SystemStatus() {
  const { data, dataUpdatedAt, isFetching } = useQuery({
    queryKey: ["readiness"],
    queryFn: ({ signal }) => fetchReadiness(signal),
    refetchInterval: REFRESH_MS,
  });

  const summary = summaryFor(data);
  const rows = rowsFor(data);

  return (
    <section
      aria-labelledby="system-status-heading"
      className="relative overflow-hidden surface-raised rounded-card border border-border"
    >
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent"
      />
      <header className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
        <div>
          <h2 id="system-status-heading" className="text-sm font-medium text-fg-secondary">
            Platform health
          </h2>
          <p role="status" aria-live="polite" className="mt-1 flex items-center gap-2 text-lg font-semibold text-fg">
            <StatusIcon tone={summary.tone} />
            {summary.text}
          </p>
        </div>
        <span
          aria-hidden
          data-testid="fetch-indicator"
          className={`mt-1.5 size-2 rounded-full bg-accent transition-opacity duration-base ${isFetching ? "animate-pulse opacity-100" : "opacity-0"}`}
        />
      </header>

      <ul aria-label="Components" className="divide-y divide-border">
        {rows.map((row) => (
          <li key={row.name} aria-label={row.name} className="flex items-center justify-between px-6 py-3.5">
            <span className="text-sm text-fg">{row.name}</span>
            <span className="flex items-center gap-2 text-sm">
              <StatusIcon tone={row.tone} />
              <span data-testid="status-label" className={toneText[row.tone]}>
                {row.label}
              </span>
            </span>
          </li>
        ))}
      </ul>

      <footer className="border-t border-border px-6 py-3 font-mono text-xs text-fg-muted">
        {dataUpdatedAt
          ? `Checked ${new Date(dataUpdatedAt).toLocaleTimeString()} · every ${REFRESH_MS / 1000}s`
          : "Waiting for first check"}
      </footer>
    </section>
  );
}
