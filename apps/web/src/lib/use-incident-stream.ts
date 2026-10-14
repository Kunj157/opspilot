"use client";

import { useEffect, useRef, useState } from "react";

/** Timeline event types the API streams (`event:` field of each SSE frame). */
export const INCIDENT_EVENT_TYPES = [
  "incident.created",
  "incident.status_changed",
  "incident.acknowledged",
  "incident.updated",
  "incident.signal_recovered",
  "incident.impact_detected",
  "incident.anomaly_detected",
  "incident.investigation_requested",
  "incident.evidence_collected",
  "incident.agent_update",
  "incident.remediation_proposed",
  "incident.investigation_finished",
  "incident.remediation_approved",
  "incident.remediation_rejected",
  "incident.remediation_executed",
  "incident.remediation_failed",
  "incident.verification_passed",
  "incident.verification_failed",
] as const;

export type StreamState = "connecting" | "live" | "reconnecting";

export type StreamedEvent = {
  id: string;
  sequence: number;
  event_type: string;
  incident: { id: string; version: number };
};

/**
 * Subscribes to an incident SSE stream. The browser's EventSource resumes
 * with Last-Event-ID after a dropped connection, so no event is lost; if the
 * server closes the stream for good (e.g. an expired session) it reopens
 * after a pause.
 */
export function useIncidentStream(
  path: string | null,
  onEvent: (event: StreamedEvent) => void,
): StreamState {
  const [state, setState] = useState<StreamState>("connecting");
  const handler = useRef(onEvent);
  useEffect(() => {
    handler.current = onEvent;
  });

  useEffect(() => {
    if (!path) return;
    let source: EventSource;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const deliver = (message: MessageEvent<string>) => {
      try {
        handler.current(JSON.parse(message.data) as StreamedEvent);
      } catch {
        // A malformed frame is skipped; the next one carries full state.
      }
    };

    const open = () => {
      source = new EventSource(path);
      source.onopen = () => setState("live");
      source.onerror = () => {
        setState("reconnecting");
        if (source.readyState === EventSource.CLOSED) retry = setTimeout(open, 5_000);
      };
      for (const type of INCIDENT_EVENT_TYPES) source.addEventListener(type, deliver);
    };
    open();

    return () => {
      clearTimeout(retry);
      source.close();
    };
  }, [path]);

  return path ? state : "connecting";
}
