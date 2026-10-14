"use client";

import type { components } from "@opspilot/api-client/schema";
import { AnimatePresence, m } from "motion/react";
import Link from "next/link";
import { useState } from "react";

import { SeverityBadge } from "@/components/incidents/badges";
import { LiveIndicator } from "@/components/incidents/live-indicator";
import { MotionScope } from "@/components/motion/motion-provider";
import { EmptyState } from "@/components/ui/empty-state";
import { duration, ease, spring } from "@/lib/motion";
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
      current.some((a) => a.sequence === event.sequence) ? current : [event as Alert, ...current].slice(0, MAX_ALERTS),
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
          <EmptyState
            title="No new alerts since you opened this page."
            description="New incident events stream in here as they happen."
          />
        ) : (
          <MotionScope>
            <ul aria-label="Live alerts" className="divide-y divide-border">
              {/* New alerts slide in from the top and briefly carry an Iris edge. */}
              <AnimatePresence>
                {alerts.map((alert) => (
                  <m.li
                    key={alert.sequence}
                    layout="position"
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, transition: { duration: duration.fast, ease: ease.out } }}
                    transition={spring.smooth}
                    className="just-arrived flex flex-col gap-1 px-5 py-3"
                  >
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
                  </m.li>
                ))}
              </AnimatePresence>
            </ul>
          </MotionScope>
        )}
      </div>
    </div>
  );
}
