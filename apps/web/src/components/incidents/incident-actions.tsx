"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useState } from "react";

import { Button } from "@/components/ui/button";

type Incident = components["schemas"]["IncidentOut"];
type Action = { key: string; label: string; primary?: boolean; run: (incident: Incident) => Promise<Result> };
type Result = { data?: Incident; response: Response; error?: unknown };

function api() {
  return createApiClient(window.location.origin);
}

const path = (incident: Incident) => ({ params: { path: { incident_id: incident.id } } });
const versioned = (incident: Incident) => ({ ...path(incident), body: { version: incident.version } });

/** Which state actions this user may take on this incident right now. */
export function availableActions(
  incident: Incident,
  permissions: { manage: boolean; investigate: boolean },
): Action[] {
  const actions: Action[] = [];
  const allowed = new Set(incident.allowed_transitions);
  if (permissions.manage && !incident.acknowledged_at && incident.status !== "RESOLVED") {
    actions.push({
      key: "acknowledge",
      label: "Acknowledge",
      run: (i) => api().POST("/api/v1/incidents/{incident_id}/acknowledge", versioned(i)),
    });
  }
  if (permissions.investigate && allowed.has("INVESTIGATING")) {
    actions.push({
      key: "investigate",
      label: "Start investigation",
      primary: true,
      run: (i) => api().POST("/api/v1/incidents/{incident_id}/investigate", versioned(i)),
    });
  }
  if (permissions.manage && allowed.has("MONITORING")) {
    actions.push({
      key: "monitor",
      label: "Move to monitoring",
      run: (i) =>
        api().PATCH("/api/v1/incidents/{incident_id}", {
          ...path(i),
          body: { version: i.version, status: "MONITORING" },
        }),
    });
  }
  if (permissions.manage && allowed.has("RESOLVED")) {
    actions.push({
      key: "resolve",
      label: "Resolve",
      primary: true,
      run: (i) => api().POST("/api/v1/incidents/{incident_id}/resolve", versioned(i)),
    });
  }
  return actions;
}

function messageFor(result: Result): string {
  const detail = (result.error as { detail?: { code?: string; message?: string } | string })?.detail;
  if (result.response.status === 409 && typeof detail === "object" && detail?.code === "stale_version") {
    return "Someone else changed this incident. It has been refreshed — check it and try again.";
  }
  if (result.response.status === 409 && typeof detail === "object" && detail?.message) return detail.message;
  if (result.response.status === 403) return "You don't have permission to do that.";
  return "The change could not be saved. Please try again.";
}

export function IncidentActions({
  incident,
  permissions,
  onChanged,
  onConflict,
}: {
  incident: Incident;
  permissions: { manage: boolean; investigate: boolean };
  onChanged: (incident: Incident) => void;
  onConflict: () => void;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const actions = availableActions(incident, permissions);
  if (actions.length === 0) return null;

  async function run(action: Action) {
    setPending(action.key);
    setError(null);
    const result = await action.run(incident);
    setPending(null);
    if (result.data) {
      onChanged(result.data);
      return;
    }
    setError(messageFor(result));
    if (result.response.status === 409) onConflict();
  }

  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label="Incident actions" className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <Button
            key={action.key}
            variant={action.primary ? "primary" : "secondary"}
            disabled={pending !== null}
            onClick={() => void run(action)}
          >
            {pending === action.key ? "Saving…" : action.label}
          </Button>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-sm text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
