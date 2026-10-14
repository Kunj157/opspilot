"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import Link from "next/link";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, ViewTransition } from "react";

import { IncidentForm } from "@/components/forms/lazy-forms";
import { SERVICES_KEY } from "@/components/services/service-catalog";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { SkeletonRows } from "@/components/ui/skeleton";
import { type Column, DataTable } from "@/components/ui/table";
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

import { LiveIndicator } from "./live-indicator";

type IncidentPage = components["schemas"]["IncidentPage"];
type Incident = IncidentPage["items"][number];

export const INCIDENTS_KEY = ["incidents"] as const;
const PAGE_SIZE = 50;

const time = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const SEVERITY_RANK = Object.fromEntries(SEVERITIES.map((s, i) => [s, i]));
const STATUS_RANK = Object.fromEntries(STATUSES.map((s, i) => [s, i]));

/** Shared view-transition name, so the title morphs from the row into the incident page. */
export function incidentTitleTransition(id: string): string {
  return `incident-title-${id}`;
}

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
      <Select value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </Select>
    </label>
  );
}

function capitalize(value: string) {
  return value[0].toUpperCase() + value.slice(1);
}

export function IncidentList({
  canManage,
  canReadUsers = false,
  currentUserId,
}: {
  canManage: boolean;
  canReadUsers?: boolean;
  currentUserId: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const filters = parseFilters(new URLSearchParams(searchParams.toString()));
  // The command palette's "New incident" action links here with ?new=1.
  const requested = canManage && searchParams.get("new") === "1";
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

  // People who have incidents assigned, for the assignee filter.
  const assignees = useQuery({
    queryKey: [...INCIDENTS_KEY, "assignees"],
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/incidents", {
        params: { query: { limit: 200 } },
        signal,
      });
      if (!data) throw new Error("assignees unavailable");
      return [...new Set(data.items.map((i) => i.assigned_user_id).filter((id): id is string => Boolean(id)))];
    },
    staleTime: 60_000,
  });
  // Names come from the user directory, which only administrators may read;
  // everyone else sees short ids (and never requests it).
  const directory = useQuery({
    enabled: canReadUsers,
    queryKey: ["users", "directory"],
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/users", {
        params: { query: { limit: 200 } },
        signal,
      });
      if (!data) throw new Error("user directory unavailable");
      return data.items;
    },
    staleTime: 300_000,
  });
  const userName = new Map((directory.data ?? []).map((u) => [u.id, u.display_name || u.email || null]));
  const assigneeLabel = (id: string) => userName.get(id) ?? `User ${id.slice(0, 8)}`;
  const otherAssignees = [
    ...new Set([
      ...(assignees.data ?? []),
      ...(directory.data ?? []).map((u) => u.id),
      ...(filters.assignee && filters.assignee !== "me" ? [filters.assignee] : []),
    ]),
  ].filter((id) => id !== currentUserId);

  const rows = incidents.data?.pages.flatMap((p) => p.items) ?? [];
  const filtered = filtersToSearch(filters) !== "";
  const serviceOf = (incident: Incident) => (incident.service_id ? (serviceName.get(incident.service_id) ?? "—") : "—");

  const columns: Column<Incident>[] = [
    {
      id: "severity",
      header: "Severity",
      cell: (incident) => <SeverityBadge severity={incident.severity} />,
      sortValue: (incident) => SEVERITY_RANK[incident.severity],
      className: "w-px whitespace-nowrap",
    },
    {
      id: "title",
      header: "Incident",
      cell: (incident) => (
        <>
          <ViewTransition name={incidentTitleTransition(incident.id)} share="morph" default="none">
            <Link
              href={`/incidents/${incident.id}`}
              className="block w-fit max-w-full truncate font-medium hover:text-accent"
            >
              {incident.title}
            </Link>
          </ViewTransition>
          {incident.source === "detector" && (
            <span className="mt-0.5 block text-xs text-fg-muted">Detected automatically</span>
          )}
          <span className="mt-1 block sm:hidden">
            <StatusBadge status={incident.status} />
          </span>
        </>
      ),
      sortValue: (incident) => incident.title.toLowerCase(),
      className: "w-full max-w-0",
    },
    {
      id: "service",
      header: "Service",
      cell: (incident) => <span className="block truncate text-fg-secondary">{serviceOf(incident)}</span>,
      sortValue: serviceOf,
      className: "hidden min-w-36 max-w-48 md:table-cell",
    },
    {
      id: "status",
      header: "Status",
      cell: (incident) => <StatusBadge status={incident.status} />,
      sortValue: (incident) => STATUS_RANK[incident.status],
      className: "hidden min-w-36 whitespace-nowrap sm:table-cell",
    },
    {
      id: "started",
      header: "Started",
      cell: (incident) => (
        <time dateTime={incident.started_at} className="font-mono text-xs text-fg-muted">
          {time.format(new Date(incident.started_at))}
        </time>
      ),
      sortValue: (incident) => Date.parse(incident.started_at),
      className: "hidden w-px whitespace-nowrap lg:table-cell",
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <LiveIndicator state={stream} />
        {canManage && <Button onClick={() => setCreating(true)}>New incident</Button>}
      </div>

      {/* overflow-clip, not hidden: the sticky table header must stick to the page scroll. */}
      <section className="surface-raised overflow-clip rounded-card border border-border">
        <form
          aria-label="Filters"
          onSubmit={(e) => e.preventDefault()}
          className="grid grid-cols-2 gap-3 border-b border-border p-5 md:grid-cols-4 xl:grid-cols-7"
        >
          <FilterSelect
            label="Status"
            value={filters.status}
            onChange={(v) => setFilters({ status: v as IncidentFilters["status"] })}
          >
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
          <FilterSelect
            label="Service"
            value={filters.service ?? ""}
            onChange={(v) => setFilters({ service: v || null })}
          >
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
          <FilterSelect
            label="Assignee"
            value={filters.assignee ?? ""}
            onChange={(v) => setFilters({ assignee: v || null })}
          >
            <option value="">Anyone</option>
            <option value="me">Me</option>
            {otherAssignees.map((id) => (
              <option key={id} value={id}>
                {assigneeLabel(id)}
              </option>
            ))}
          </FilterSelect>
          <label className="flex flex-col gap-1.5 text-xs text-fg-secondary">
            Started from
            <Input
              type="date"
              value={filters.since ?? ""}
              onChange={(e) => setFilters({ since: e.target.value || null })}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-xs text-fg-secondary">
            Started until
            <Input
              type="date"
              value={filters.until ?? ""}
              onChange={(e) => setFilters({ until: e.target.value || null })}
            />
          </label>
        </form>

        {incidents.isPending && <SkeletonRows rows={5} />}
        {incidents.isError && (
          <div role="alert" className="flex flex-col items-center gap-3 px-5 py-10 text-sm">
            <p className="text-critical">Incidents could not be loaded.</p>
            <Button variant="secondary" size="sm" onClick={() => void incidents.refetch()}>
              Try again
            </Button>
          </div>
        )}
        {incidents.isSuccess && rows.length === 0 && (
          <EmptyState
            tone={filtered ? "neutral" : "positive"}
            title={filtered ? "No incidents match these filters." : "No active incidents. All quiet."}
            description={filtered ? "Widen the filters or clear them to see more." : "New incidents appear here live."}
          />
        )}
        {rows.length > 0 && (
          <DataTable
            caption="Incidents"
            columns={columns}
            rows={rows}
            rowKey={(incident) => incident.id}
            rowHref={(incident) => `/incidents/${incident.id}`}
            onNavigate={(href) => router.push(href)}
          />
        )}
        {incidents.hasNextPage && (
          <div className="border-t border-border p-4 text-center">
            <Button
              variant="secondary"
              size="sm"
              disabled={incidents.isFetchingNextPage}
              onClick={() => void incidents.fetchNextPage()}
            >
              {incidents.isFetchingNextPage ? "Loading…" : "Load more"}
            </Button>
          </div>
        )}
      </section>

      <Modal
        open={creating || requested}
        title="New incident"
        onClose={() => {
          setCreating(false);
          if (requested) router.replace(`${pathname}${filtersToSearch(filters)}`, { scroll: false });
        }}
      >
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
