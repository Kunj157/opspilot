"use client";

import { createApiClient } from "@opspilot/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { SeverityBadge, StatusBadge } from "@/components/incidents/badges";
import { Modal } from "@/components/ui/modal";

import { HealthBadge } from "./health-badge";
import { SERVICES_KEY } from "./service-catalog";
import { ServiceForm } from "./service-form";

const ACTIVE = ["DETECTED", "INVESTIGATING", "AWAITING_APPROVAL", "REMEDIATING", "VERIFYING", "MONITORING", "REJECTED"] as const;

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="mt-1 truncate font-mono text-sm">{value || "—"}</dd>
    </div>
  );
}

export function ServiceDetail({ canManage }: { canManage: boolean }) {
  const { serviceId } = useParams<{ serviceId: string }>();
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();
  const api = () => createApiClient(window.location.origin);

  const service = useQuery({
    queryKey: [...SERVICES_KEY, serviceId],
    queryFn: async ({ signal }) => {
      const { data, response } = await api().GET("/api/v1/services/{service_id}", {
        params: { path: { service_id: serviceId } },
        signal,
      });
      if (response.status === 404 || response.status === 422) return null;
      if (!data) throw new Error("service unavailable");
      return data;
    },
  });
  const incidents = useQuery({
    queryKey: ["incidents", { service: serviceId, active: true }],
    enabled: Boolean(service.data),
    queryFn: async ({ signal }) => {
      const { data } = await api().GET("/api/v1/incidents", {
        params: { query: { service_id: serviceId, status: [...ACTIVE], limit: 50 } },
        signal,
      });
      if (!data) throw new Error("incidents unavailable");
      return data.items;
    },
  });

  if (service.isPending) return <div aria-hidden className="h-64 animate-pulse rounded-card bg-surface-2" />;
  if (service.isError)
    return (
      <p role="alert" className="rounded-card border border-border bg-surface-2 p-5 text-sm text-critical">
        This service could not be loaded.
      </p>
    );
  if (!service.data)
    return (
      <div className="rounded-card border border-border bg-surface-2 p-8 text-center">
        <p className="font-medium">Service not found</p>
        <Link href="/services" className="mt-2 inline-block text-sm text-accent hover:underline">
          Back to services
        </Link>
      </div>
    );

  const s = service.data;
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-3xl font-semibold tracking-tight sm:text-4xl">{s.name}</h1>
          <p className="mt-2 flex items-center gap-3 font-mono text-xs text-fg-muted">
            {s.slug} <HealthBadge health={s.health_status} />
          </p>
        </div>
        {canManage && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded-sm border border-border px-4 py-2 text-sm text-fg-secondary hover:border-border-strong hover:text-fg"
          >
            Edit service
          </button>
        )}
      </div>

      {s.description && <p className="max-w-2xl text-fg-secondary">{s.description}</p>}

      <dl className="grid gap-5 rounded-card border border-border bg-surface-2 p-5 shadow-2 sm:grid-cols-2 lg:grid-cols-4">
        <Fact label="Owner team" value={s.owner_team} />
        <Fact label="Namespace" value={s.namespace} />
        <Fact label="Deployment" value={s.deployment_name} />
        <Fact label="Repository" value={s.repository_url} />
      </dl>

      <section aria-labelledby="service-incidents" className="rounded-card border border-border bg-surface-2 shadow-3">
        <h2 id="service-incidents" className="border-b border-border px-5 py-4 text-sm font-medium text-fg-secondary">
          Active incidents
        </h2>
        {incidents.isSuccess && incidents.data.length === 0 && (
          <p className="px-5 py-8 text-center text-sm text-fg-muted">No active incidents for this service.</p>
        )}
        {incidents.isSuccess && incidents.data.length > 0 && (
          <ul aria-label="Active incidents" className="divide-y divide-border">
            {incidents.data.map((incident) => (
              <li key={incident.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5">
                <SeverityBadge severity={incident.severity} />
                <span className="min-w-0 flex-1 truncate text-sm">{incident.title}</span>
                <StatusBadge status={incident.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <Modal open={editing} title="Edit service" onClose={() => setEditing(false)}>
        <ServiceForm
          service={s}
          onSaved={(saved) => {
            setEditing(false);
            queryClient.setQueryData([...SERVICES_KEY, serviceId], saved);
            void queryClient.invalidateQueries({ queryKey: SERVICES_KEY, exact: true });
          }}
        />
      </Modal>
    </div>
  );
}
