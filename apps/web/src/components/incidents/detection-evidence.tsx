"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";

type Detection = components["schemas"]["DetectionOut"];

const OUTCOME: Record<string, string> = {
  triggered: "Triggered",
  ongoing: "Still failing",
  recovered: "Recovered",
};

const percent = (value: unknown) => (typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—");
const time = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label}>
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="mt-1 font-mono text-sm">{children}</dd>
    </div>
  );
}

function summary(latest: Detection): string {
  const rate = latest.features.error_rate;
  if (latest.outcome === "recovered") return `Error rate back to ${percent(rate)}`;
  const threshold = latest.threshold ? `${Math.round(latest.threshold * 100)}%` : "the";
  return `${percent(rate)} of requests failing, ${(latest.score ?? 0).toFixed(1)}× the ${threshold} threshold`;
}

/**
 * Why the detector opened this incident: its readings, newest first. Readings
 * from callers affected by this incident are listed too, labelled by service.
 */
export function DetectionEvidence({
  incidentId,
  serviceId,
  serviceNames,
}: {
  incidentId: string;
  serviceId: string | null;
  serviceNames: Map<string, string>;
}) {
  const detections = useQuery({
    queryKey: ["incident-detections", incidentId],
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/incidents/{incident_id}/detections", {
        params: { path: { incident_id: incidentId } },
        signal,
      });
      if (!data) throw new Error("detections unavailable");
      return data.items;
    },
    // Readings are not timeline events, so they are polled rather than streamed.
    refetchInterval: 15_000,
  });

  return (
    <Card as="section" aria-labelledby="detection-heading" className="p-5">
      <h2 id="detection-heading" className="text-sm font-medium text-fg-secondary">
        Detection
      </h2>
      {detections.isPending && <div aria-hidden className="mt-4 h-20 animate-pulse rounded-sm bg-surface-3" />}
      {detections.isError && (
        <p role="alert" className="mt-4 text-sm text-critical">
          Detector readings could not be loaded.
        </p>
      )}
      {detections.isSuccess && detections.data.length === 0 && (
        <p className="mt-4 text-sm text-fg-muted">No detector readings recorded for this incident.</p>
      )}
      {detections.isSuccess && detections.data.length > 0 && (
        <Evidence items={detections.data} serviceId={serviceId} serviceNames={serviceNames} />
      )}
    </Card>
  );
}

function Evidence({
  items,
  serviceId,
  serviceNames,
}: {
  items: Detection[];
  serviceId: string | null;
  serviceNames: Map<string, string>;
}) {
  const own = items.filter((d) => d.service_id === serviceId);
  const readings = own.length ? own : items;
  const latest = readings[0];
  const peak = Math.max(...readings.map((d) => Number(d.features.error_rate ?? 0)));
  return (
    <div className="mt-3 flex flex-col gap-5">
      <p className="text-lg font-medium">{summary(latest)}</p>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Fact label="Peak error rate">{percent(peak)}</Fact>
        <Fact label="Traffic">
          {typeof latest.features.requests_per_second === "number"
            ? `${latest.features.requests_per_second.toFixed(1)} req/s`
            : "—"}
        </Fact>
        <Fact label="Rule">
          {latest.detector} · {latest.model_version ?? "—"}
        </Fact>
        <Fact label="Last evaluated">
          <time dateTime={latest.window_end}>{time.format(new Date(latest.window_end))}</time>
        </Fact>
      </dl>
      <ul aria-label="Detector readings" className="divide-y divide-border rounded-sm border border-border">
        {items.slice(0, 10).map((d) => (
          <li key={d.id} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 px-3 py-2 text-sm">
            <span className={d.outcome === "recovered" ? "text-healthy" : "text-fg"}>
              {OUTCOME[d.outcome] ?? d.outcome}
              {d.service_id !== serviceId && (
                <span className="ml-2 text-xs text-fg-muted">
                  {serviceNames.get(d.service_id) ?? "Another service"} (affected)
                </span>
              )}
            </span>
            <span className="font-mono text-xs text-fg-secondary">{percent(d.features.error_rate)} errors</span>
            <time dateTime={d.window_end} className="font-mono text-xs text-fg-muted">
              {time.format(new Date(d.window_end))}
            </time>
          </li>
        ))}
      </ul>
    </div>
  );
}
