"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SERVICES_KEY } from "@/components/services/service-catalog";
import { type StreamedEvent, useIncidentStream } from "@/lib/use-incident-stream";

import { SeverityBadge, StatusBadge } from "./badges";
import { IncidentActions } from "./incident-actions";
import { INCIDENTS_KEY } from "./incident-list";
import { IncidentTimeline } from "./incident-timeline";
import { LiveIndicator } from "./live-indicator";

type Incident = components["schemas"]["IncidentOut"];
type Event = components["schemas"]["EventOut"];

/** "3h 12m" style duration between two instants. */
export function formatDuration(fromIso: string, to: Date): string {
  const minutes = Math.max(0, Math.floor((to.getTime() - new Date(fromIso).getTime()) / 60_000));
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

function useNow(intervalMs: number) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="mt-1 text-sm">{children}</dd>
    </div>
  );
}

export function IncidentDetail({ permissions }: { permissions: { manage: boolean; investigate: boolean } }) {
  const { incidentId } = useParams<{ incidentId: string }>();
  const queryClient = useQueryClient();
  const now = useNow(30_000);
  const incidentKey = [...INCIDENTS_KEY, "detail", incidentId];
  const eventsKey = [...INCIDENTS_KEY, "events", incidentId];

  const incident = useQuery({
    queryKey: incidentKey,
    queryFn: async ({ signal }) => {
      const { data, response } = await createApiClient(window.location.origin).GET("/api/v1/incidents/{incident_id}", {
        params: { path: { incident_id: incidentId } },
        signal,
      });
      if (response.status === 404 || response.status === 422) return null;
      if (!data) throw new Error("incident unavailable");
      return data;
    },
  });
  const events = useQuery({
    queryKey: eventsKey,
    enabled: Boolean(incident.data),
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/incidents/{incident_id}/events", {
        params: { path: { incident_id: incidentId } },
        signal,
      });
      if (!data) throw new Error("timeline unavailable");
      return data.items;
    },
  });
  const services = useQuery({
    queryKey: SERVICES_KEY,
    enabled: Boolean(incident.data?.service_id),
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/services", { signal });
      if (!data) throw new Error("services unavailable");
      return data.items;
    },
  });

  const stream = useIncidentStream(incident.data ? `/api/v1/incidents/${incidentId}/stream` : null, (streamed: StreamedEvent) => {
    const { incident: latest, ...event } = streamed as StreamedEvent & Event & { incident: Incident };
    queryClient.setQueryData<Incident | null>(incidentKey, (current) =>
      !current || latest.version >= current.version ? latest : current,
    );
    queryClient.setQueryData<Event[]>(eventsKey, (current = []) =>
      current.some((e) => e.sequence === event.sequence) ? current : [...current, event as Event],
    );
  });

  if (incident.isPending) return <div aria-hidden className="h-96 animate-pulse rounded-card bg-surface-2" />;
  if (incident.isError)
    return (
      <p role="alert" className="rounded-card border border-border bg-surface-2 p-5 text-sm text-critical">
        This incident could not be loaded.
      </p>
    );
  if (!incident.data)
    return (
      <div className="rounded-card border border-border bg-surface-2 p-8 text-center">
        <p className="font-medium">Incident not found</p>
        <Link href="/incidents" className="mt-2 inline-block text-sm text-accent hover:underline">
          Back to incidents
        </Link>
      </div>
    );

  const i = incident.data;
  const service = services.data?.find((s) => s.id === i.service_id);
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <SeverityBadge severity={i.severity} />
          <StatusBadge status={i.status} />
          <LiveIndicator state={stream} />
        </div>
        <h1 className="text-3xl font-semibold tracking-tight break-words sm:text-4xl">{i.title}</h1>
        {i.description && <p className="max-w-2xl text-fg-secondary">{i.description}</p>}
        <dl className="grid grid-cols-2 gap-5 rounded-card border border-border bg-surface-2 p-5 shadow-2 lg:grid-cols-4">
          <Fact label="Service">
            {i.service_id ? (
              <Link href={`/services/${i.service_id}`} className="text-accent hover:underline">
                {service?.name ?? "View service"}
              </Link>
            ) : (
              "Not yet known"
            )}
          </Fact>
          <Fact label={i.resolved_at ? "Duration" : "Open for"}>
            <span className="font-mono">
              {formatDuration(i.started_at, i.resolved_at ? new Date(i.resolved_at) : now)}
            </span>
          </Fact>
          <Fact label="Acknowledged">{i.acknowledged_at ? "Yes" : "Not yet"}</Fact>
          <Fact label="Source">
            <span className="capitalize">{i.source}</span>
          </Fact>
        </dl>
        <IncidentActions
          incident={i}
          permissions={permissions}
          onChanged={(updated) => {
            queryClient.setQueryData(incidentKey, updated);
            void queryClient.invalidateQueries({ queryKey: eventsKey });
          }}
          onConflict={() => void queryClient.invalidateQueries({ queryKey: incidentKey })}
        />
      </header>

      <section aria-labelledby="timeline-heading" className="rounded-card border border-border bg-surface-1 shadow-3">
        <h2 id="timeline-heading" className="border-b border-border px-5 py-4 text-sm font-medium text-fg-secondary">
          Timeline
        </h2>
        {events.isPending && <div aria-hidden className="m-5 h-24 animate-pulse rounded-card bg-surface-2" />}
        {events.isError && (
          <p role="alert" className="px-5 py-8 text-center text-sm text-critical">
            The timeline could not be loaded.
          </p>
        )}
        {events.isSuccess && <IncidentTimeline events={events.data} />}
      </section>
    </div>
  );
}
