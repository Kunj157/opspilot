"use client";

import type { components } from "@opspilot/api-client/schema";
import Link from "next/link";
import { useState } from "react";

import { SeverityBadge } from "@/components/incidents/badges";
import { LiveIndicator } from "@/components/incidents/live-indicator";
import { type StreamedEvent, useIncidentStream } from "@/lib/use-incident-stream";

type Incident = components["schemas"]["IncidentOut"];
type Alert = StreamedEvent & { title: string; created_at: string; incident: Incident };

const MAX_ALERTS = 8;
const time = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });

/** Incident events for the whole organization as they happen, newest first. */
export function AlertStream({ onEvent }: { onEvent: (event: StreamedEvent) => void }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const state = useIncidentStream("/api/v1/incidents/stream", (event) => {
    onEvent(event);
    setAlerts((current) =>
      current.some((a) => a.sequence === event.sequence)
        ? current
        : [event as Alert, ...current].slice(0, MAX_ALERTS),
    );
  });

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
        <h2 className="text-sm font-medium text-fg-secondary">Live alerts</h2>
        <LiveIndicator state={state} />
      </div>
      {/* Always mounted, so the first alert is announced too. */}
      <div aria-live="polite" className="flex-1">
        {alerts.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-fg-muted">
            No new alerts since you opened this page.
          </p>
        ) : (
          <ul aria-label="Live alerts" className="divide-y divide-border">
            {alerts.map((alert) => (
              <li key={alert.sequence} className="flex flex-col gap-1 px-5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <SeverityBadge severity={alert.incident.severity} />
                  <time dateTime={alert.created_at} className="font-mono text-xs text-fg-muted">
                    {time.format(new Date(alert.created_at))}
                  </time>
                </div>
                <Link href={`/incidents/${alert.incident.id}`} className="truncate text-sm hover:text-accent">
                  {alert.incident.title}
                </Link>
                <p className="text-xs text-fg-secondary">{alert.title}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
