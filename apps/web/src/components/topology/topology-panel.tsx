"use client";

import { createApiClient } from "@opspilot/api-client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { HealthBadge } from "@/components/services/health-badge";
import { Card } from "@/components/ui/card";

import { connections, layout, type Topology } from "./model";
import { ServiceTopology2D } from "./service-topology-2d";

export const TOPOLOGY_KEY = ["topology"] as const;

function Names({ label, ids, topology }: { label: string; ids: string[]; topology: Topology }) {
  const names = new Map(topology.nodes.map((n) => [n.id, n.name]));
  return (
    <div>
      <p className="text-xs text-fg-muted">{label}</p>
      {ids.length === 0 ? (
        <p className="mt-1 text-sm text-fg-secondary">None</p>
      ) : (
        <ul aria-label={label} className="mt-1 flex flex-wrap gap-1.5">
          {ids.map((id) => (
            <li key={id} className="rounded-sm bg-surface-3 px-2 py-0.5 text-xs">
              {names.get(id)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Details({ topology, id }: { topology: Topology; id: string | null }) {
  const node = topology.nodes.find((n) => n.id === id);
  if (!node) {
    return <p className="text-sm text-fg-muted">Select a service to see what it calls and what calls it.</p>;
  }
  const { dependencies, dependents } = connections(topology, node.id);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="font-medium">{node.name}</h3>
        <p className="font-mono text-xs text-fg-muted">{node.slug}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <HealthBadge health={node.health_status} />
        <span className="text-xs text-fg-secondary">
          {node.active_incidents} active incident{node.active_incidents === 1 ? "" : "s"}
        </span>
        {node.investigating && <span className="text-xs text-accent">Under investigation</span>}
      </div>
      <Names label="Calls" ids={dependencies} topology={topology} />
      <Names label="Called by" ids={dependents} topology={topology} />
      <Link href={`/services/${node.id}`} aria-label={`Open ${node.name}`} className="text-sm text-accent hover:underline">
        Open service →
      </Link>
    </div>
  );
}

/** Small screens: the same information as a list, ordered like the map. */
function TopologyList({ topology }: { topology: Topology }) {
  const nodes = new Map(topology.nodes.map((n) => [n.id, n]));
  return (
    <ul aria-label="Services by dependency" className="divide-y divide-border sm:hidden">
      {layout(topology).order.map((id) => {
        const node = nodes.get(id)!;
        const calls = connections(topology, id).dependencies.map((d) => nodes.get(d)!.name);
        return (
          <li key={id} className="flex flex-col gap-1 px-5 py-3">
            <div className="flex items-center justify-between gap-3">
              <Link href={`/services/${id}`} className="truncate text-sm font-medium hover:text-accent">
                {node.name}
              </Link>
              <HealthBadge health={node.health_status} />
            </div>
            <p className="text-xs text-fg-muted">{calls.length ? `Calls ${calls.join(", ")}` : "Calls no other service"}</p>
          </li>
        );
      })}
    </ul>
  );
}

export function TopologyPanel() {
  const router = useRouter();
  const [selected, setSelected] = useState<string | null>(null);
  const topology = useQuery({
    queryKey: TOPOLOGY_KEY,
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/topology", { signal });
      if (!data) throw new Error("topology unavailable");
      return data;
    },
    refetchInterval: 30_000,
  });

  return (
    <Card as="section" aria-labelledby="topology-heading" className="shadow-3">
      <h2 id="topology-heading" className="border-b border-border px-5 py-4 text-sm font-medium text-fg-secondary">
        Service topology
      </h2>
      {topology.isPending && <div aria-hidden className="m-5 h-64 animate-pulse rounded-card bg-surface-3" />}
      {topology.isError && (
        <p role="alert" className="px-5 py-10 text-center text-sm text-critical">
          The service topology could not be loaded.
        </p>
      )}
      {topology.isSuccess && topology.data.nodes.length === 0 && (
        <p className="px-5 py-10 text-center text-sm text-fg-muted">
          No services to map yet. Add services and their dependencies in the catalog.
        </p>
      )}
      {topology.isSuccess && topology.data.nodes.length > 0 && (
        <>
          <TopologyList topology={topology.data} />
          <div className="hidden gap-5 p-5 sm:grid lg:grid-cols-[1fr_16rem]">
            <div className="min-w-0 overflow-x-auto">
              <ServiceTopology2D
                topology={topology.data}
                selectedId={selected}
                onSelect={setSelected}
                onOpen={(id) => router.push(`/services/${id}`)}
              />
            </div>
            <section aria-label="Selected service" className="rounded-card border border-border bg-surface-1 p-4">
              <Details topology={topology.data} id={selected} />
            </section>
          </div>
        </>
      )}
    </Card>
  );
}
