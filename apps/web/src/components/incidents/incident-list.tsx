"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import Link from "next/link";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { SERVICES_KEY } from "@/components/services/service-catalog";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import {
  filtersToSearch,
  type IncidentFilters,
  parseFilters,
  SEVERITIES,
  SOURCES,
  STATUSES,
  toApiQuery,
} from "@/lib/incident-filters";
import { useIncidentStream } from "@/lib/use-incident-stream";

import { SeverityBadge, StatusBadge, statusLabel } from "./badges";
import { IncidentForm } from "./incident-form";
import { LiveIndicator } from "./live-indicator";

type IncidentPage = components["schemas"]["IncidentPage"];

export const INCIDENTS_KEY = ["incidents"] as const;
const PAGE_SIZE = 50;

const time = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const selectClass =
  "h-9 w-full rounded-sm border border-border bg-surface-1 px-2 text-sm text-fg focus:border-accent focus:outline-none";

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-xs text-fg-secondary">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className={selectClass}>
        {children}
      </select>
    </label>
  );
}

function capitalize(value: string) {
  return value[0].toUpperCase() + value.slice(1);
}

export function IncidentList({ canManage, currentUserId }: { canManage: boolean; currentUserId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const filters = parseFilters(new URLSearchParams(useSearchParams().toString()));
  const queryClient = useQueryClient();
  const toast = useToast();
  const [creating, setCreating] = useState(false);

  const setFilters = (change: Partial<IncidentFilters>) =>
    router.replace(`${pathname}${filtersToSearch({ ...filters, ...change })}`, { scroll: false });

  const services = useQuery({
    queryKey: SERVICES_KEY,
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/services", { signal });
      if (!data) throw new Error("services unavailable");
      return data.items;
    },
  });
  const serviceName = new Map(services.data?.map((s) => [s.id, s.name]));

  const incidents = useInfiniteQuery<IncidentPage>({
    queryKey: [...INCIDENTS_KEY, "list", filters],
    queryFn: async ({ pageParam, signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/incidents", {
        params: {
          query: { ...toApiQuery(filters, currentUserId), limit: PAGE_SIZE, cursor: pageParam as string | undefined },
        },
        signal,
      });
      if (!data) throw new Error("incidents unavailable");
      return data;
    },
    initialPageParam: undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  // Any change in the organization may move an incident into or out of this view.
  const stream = useIncidentStream("/api/v1/incidents/stream", () => {
    void queryClient.invalidateQueries({ queryKey: INCIDENTS_KEY });
  });

  const rows = incidents.data?.pages.flatMap((p) => p.items) ?? [];
  const filtered = filtersToSearch(filters) !== "";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <LiveIndicator state={stream} />
        {canManage && (
          <Button
            onClick={() => setCreating(true)}
          >
            New incident
          </Button>
        )}
      </div>

      <section className="overflow-hidden rounded-card border border-border bg-surface-2 shadow-3">
        <form
          aria-label="Filters"
          onSubmit={(e) => e.preventDefault()}
          className="grid grid-cols-2 gap-3 border-b border-border p-5 lg:grid-cols-6"
        >
          <FilterSelect label="Status" value={filters.status} onChange={(v) => setFilters({ status: v as IncidentFilters["status"] })}>
            <option value="active">Active</option>
            <option value="all">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </FilterSelect>
          <FilterSelect
            label="Severity"
            value={filters.severity[0] ?? ""}
            onChange={(v) => setFilters({ severity: v ? [v as IncidentFilters["severity"][number]] : [] })}
          >
            <option value="">Any</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {capitalize(s)}
              </option>
            ))}
          </FilterSelect>
          <FilterSelect label="Service" value={filters.service ?? ""} onChange={(v) => setFilters({ service: v || null })}>
            <option value="">Any</option>
            {services.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </FilterSelect>
          <FilterSelect
            label="Source"
            value={filters.source ?? ""}
            onChange={(v) => setFilters({ source: (v || null) as IncidentFilters["source"] })}
          >
            <option value="">Any</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {capitalize(s)}
              </option>
            ))}
          </FilterSelect>
          <label className="flex flex-col gap-1.5 text-xs text-fg-secondary">
            Started from
            <input
              type="date"
              value={filters.since ?? ""}
              onChange={(e) => setFilters({ since: e.target.value || null })}
              className={selectClass}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-xs text-fg-secondary">
            Started until
            <input
              type="date"
              value={filters.until ?? ""}
              onChange={(e) => setFilters({ until: e.target.value || null })}
              className={selectClass}
            />
          </label>
          <label className="col-span-2 flex items-center gap-2 text-sm text-fg-secondary lg:col-span-6">
            <input
              type="checkbox"
              checked={filters.mine}
              onChange={(e) => setFilters({ mine: e.target.checked })}
              className="size-4 accent-[var(--accent)]"
            />
            Assigned to me
          </label>
        </form>

        {incidents.isPending && (
          <div aria-hidden className="flex flex-col gap-2 p-5">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded-sm bg-surface-3" />
            ))}
          </div>
        )}
        {incidents.isError && (
          <div role="alert" className="flex flex-col items-center gap-3 px-5 py-10 text-sm">
            <p className="text-critical">Incidents could not be loaded.</p>
            <button
              type="button"
              onClick={() => void incidents.refetch()}
              className="rounded-sm border border-border px-3 py-1.5 text-fg-secondary hover:border-border-strong hover:text-fg"
            >
              Try again
            </button>
          </div>
        )}
        {incidents.isSuccess && rows.length === 0 && (
          <p className="px-5 py-12 text-center text-sm text-fg-muted">
            {filtered ? "No incidents match these filters." : "No active incidents. All quiet."}
          </p>
        )}
        {rows.length > 0 && (
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Incidents</caption>
            <thead className="text-xs text-fg-muted">
              <tr className="border-b border-border">
                <th scope="col" className="w-px whitespace-nowrap px-5 py-3 font-medium">Severity</th>
                <th scope="col" className="w-full px-2 py-3 font-medium">Incident</th>
                <th scope="col" className="hidden min-w-36 px-2 py-3 font-medium md:table-cell">Service</th>
                <th scope="col" className="hidden min-w-36 px-2 py-3 font-medium sm:table-cell">Status</th>
                <th scope="col" className="hidden w-px whitespace-nowrap px-5 py-3 font-medium lg:table-cell">Started</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((incident) => (
                <tr key={incident.id} className="transition-colors duration-base hover:bg-surface-3">
                  <td className="w-px whitespace-nowrap px-5 py-3.5 align-top">
                    <SeverityBadge severity={incident.severity} />
                  </td>
                  <td className="max-w-0 px-2 py-3.5">
                    <Link href={`/incidents/${incident.id}`} className="block truncate font-medium hover:text-accent">
                      {incident.title}
                    </Link>
                    {incident.source === "detector" && (
                      <span className="mt-0.5 block text-xs text-fg-muted">Detected automatically</span>
                    )}
                    <span className="mt-1 block sm:hidden">
                      <StatusBadge status={incident.status} />
                    </span>
                  </td>
                  <td className="hidden max-w-48 truncate px-2 py-3.5 text-fg-secondary md:table-cell">
                    {incident.service_id ? (serviceName.get(incident.service_id) ?? "—") : "—"}
                  </td>
                  <td className="hidden whitespace-nowrap px-2 py-3.5 sm:table-cell">
                    <StatusBadge status={incident.status} />
                  </td>
                  <td className="hidden whitespace-nowrap px-5 py-3.5 font-mono text-xs text-fg-muted lg:table-cell">
                    <time dateTime={incident.started_at}>{time.format(new Date(incident.started_at))}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {incidents.hasNextPage && (
          <div className="border-t border-border p-4 text-center">
            <button
              type="button"
              disabled={incidents.isFetchingNextPage}
              onClick={() => void incidents.fetchNextPage()}
              className="rounded-sm border border-border px-3 py-1.5 text-sm text-fg-secondary hover:border-border-strong hover:text-fg disabled:opacity-50"
            >
              {incidents.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </section>

      <Modal open={creating} title="New incident" onClose={() => setCreating(false)}>
        <IncidentForm
          services={services.data ?? []}
          onCreated={(incident) => {
            setCreating(false);
            toast(`Incident “${incident.title}” created`);
            void queryClient.invalidateQueries({ queryKey: INCIDENTS_KEY });
            router.push(`/incidents/${incident.id}`);
          }}
        />
      </Modal>
    </div>
  );
}
