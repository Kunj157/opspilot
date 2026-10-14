"use client";

import { createApiClient, type AuditLogItem, type AuditLogPage } from "@opspilot/api-client";
import { useInfiniteQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const PAGE_SIZE = 25;

type Filters = { action: string; resourceType: string; since: string };
const EMPTY_FILTERS: Filters = { action: "", resourceType: "", since: "" };

class ForbiddenError extends Error {}

async function fetchPage(filters: Filters, cursor: string | undefined, signal: AbortSignal) {
  const api = createApiClient(window.location.origin);
  const { data, response } = await api.GET("/api/v1/audit-logs", {
    params: {
      query: {
        limit: PAGE_SIZE,
        action: filters.action || undefined,
        resource_type: filters.resourceType || undefined,
        since: filters.since ? new Date(filters.since).toISOString() : undefined,
        cursor,
      },
    },
    signal,
  });
  if (response.status === 403) throw new ForbiddenError();
  if (!data) throw new Error(`HTTP ${response.status}`);
  return data;
}

const timeFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "medium",
});

function Entry({ entry }: { entry: AuditLogItem }) {
  return (
    <li
      aria-label={`${entry.action} at ${entry.created_at}`}
      className="grid gap-x-6 gap-y-1 px-5 py-3.5 sm:grid-cols-[11rem_1fr_auto] sm:items-baseline"
    >
      <time dateTime={entry.created_at} className="font-mono text-xs text-fg-muted">
        {timeFormat.format(new Date(entry.created_at))}
      </time>
      <div className="min-w-0">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="rounded-sm bg-accent-subtle px-1.5 py-0.5 font-mono text-xs text-accent">
            {entry.action}
          </span>
          <span className="truncate text-sm text-fg">{entry.resource_id ?? entry.resource_type}</span>
        </p>
        <p className="mt-1 truncate text-xs text-fg-secondary">
          <span className="capitalize">{entry.actor_type}</span> · <span className="font-mono">{entry.actor_id}</span>
          {entry.ip_address && <> · {entry.ip_address}</>}
        </p>
      </div>
      {entry.request_id && (
        <span className="truncate font-mono text-xs text-fg-muted sm:max-w-40" title="Request ID">
          {entry.request_id}
        </span>
      )}
    </li>
  );
}

function Field({
  label,
  name,
  type = "text",
  placeholder,
}: {
  label: string;
  name: keyof Filters;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-xs text-fg-secondary">
      {label}
      <Input name={name} type={type} placeholder={placeholder} />
    </label>
  );
}

export function AuditLogExplorer() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);

  const query = useInfiniteQuery<AuditLogPage>({
    queryKey: ["audit-logs", filters],
    queryFn: ({ pageParam, signal }) => fetchPage(filters, pageParam as string | undefined, signal),
    initialPageParam: undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFilters({
      action: String(form.get("action") ?? "").trim(),
      resourceType: String(form.get("resourceType") ?? "").trim(),
      since: String(form.get("since") ?? ""),
    });
  }

  const entries = query.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section className="surface-raised overflow-clip rounded-card border border-border">
      <form
        onSubmit={applyFilters}
        aria-label="Filters"
        className="grid gap-3 border-b border-border p-5 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end"
      >
        <Field label="Action" name="action" placeholder="e.g. user.provisioned" />
        <Field label="Resource type" name="resourceType" placeholder="e.g. user" />
        <Field label="Since" name="since" type="datetime-local" />
        <Button type="submit">Apply filters</Button>
      </form>

      {query.isPending && (
        <p role="status" className="px-5 py-10 text-center text-sm text-fg-muted">
          Loading audit records…
        </p>
      )}

      {query.isError &&
        (query.error instanceof ForbiddenError ? (
          <p role="alert" className="px-5 py-10 text-center text-sm text-fg-secondary">
            You don&apos;t have access to the audit log.
          </p>
        ) : (
          <div role="alert" className="flex flex-col items-center gap-3 px-5 py-10 text-sm">
            <p className="text-critical">The audit log could not be loaded.</p>
            <button
              type="button"
              onClick={() => void query.refetch()}
              className="rounded-sm border border-border px-3 py-1.5 text-fg-secondary hover:border-border-strong hover:text-fg"
            >
              Try again
            </button>
          </div>
        ))}

      {query.isSuccess && entries.length === 0 && (
        <p className="px-5 py-10 text-center text-sm text-fg-muted">No audit records match these filters.</p>
      )}

      {entries.length > 0 && (
        <ul aria-label="Audit records" className="divide-y divide-border">
          {entries.map((entry) => (
            <Entry key={entry.id} entry={entry} />
          ))}
        </ul>
      )}

      {query.hasNextPage && (
        <div className="border-t border-border p-4 text-center">
          <button
            type="button"
            onClick={() => void query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
            className="rounded-sm border border-border px-4 py-1.5 text-sm text-fg-secondary hover:border-border-strong hover:text-fg disabled:opacity-50"
          >
            {query.isFetchingNextPage ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </section>
  );
}
