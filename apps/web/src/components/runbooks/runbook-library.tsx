"use client";

import { createApiClient } from "@opspilot/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { RunbookForm } from "@/components/forms/lazy-forms";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";

export const RUNBOOKS_KEY = ["runbooks"] as const;

function api() {
  return createApiClient(window.location.origin);
}

function Services({ slugs }: { slugs: string[] }) {
  return (
    <span className="flex flex-wrap gap-1">
      {slugs.map((s) => (
        <span key={s} className="rounded-sm bg-surface-3 px-1.5 py-0.5 font-mono text-[11px] text-fg-secondary">
          {s}
        </span>
      ))}
    </span>
  );
}

function SearchResults({ query }: { query: string }) {
  const results = useQuery({
    queryKey: ["runbook-search", query],
    queryFn: async ({ signal }) => {
      const { data } = await api().GET("/api/v1/runbooks/search", { params: { query: { q: query, limit: 10 } }, signal });
      if (!data) throw new Error("search failed");
      return data.items;
    },
  });
  if (results.isPending) return <p role="status" className="py-8 text-center text-sm text-fg-muted">Searching…</p>;
  if (results.isError)
    return (
      <p role="alert" className="py-8 text-center text-sm text-critical">
        Search is unavailable right now.
      </p>
    );
  if (results.data.length === 0)
    return <p className="py-8 text-center text-sm text-fg-muted">No runbook matches “{query}”.</p>;
  return (
    <ol aria-label="Search results" className="flex flex-col gap-3">
      {results.data.map((hit) => (
        <li key={`${hit.runbook_id}-${hit.heading}`}>
          <Card className="p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <Link href={`/runbooks/${hit.runbook_id}`} className="font-medium hover:text-accent">
                {hit.title}
              </Link>
              <span className="font-mono text-xs text-fg-muted">
                v{hit.version} · {hit.heading} · {(hit.score * 100).toFixed(0)}% match
              </span>
            </div>
            {hit.flagged && (
              <p className="mt-2 text-xs text-degraded">
                ▲ This section contains instruction-like text and is never followed automatically.
              </p>
            )}
            <p className="mt-2 line-clamp-3 text-sm text-fg-secondary">{hit.content}</p>
          </Card>
        </li>
      ))}
    </ol>
  );
}

export function RunbookLibrary({ canManage }: { canManage: boolean }) {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const runbooks = useQuery({
    queryKey: RUNBOOKS_KEY,
    queryFn: async ({ signal }) => {
      const { data } = await api().GET("/api/v1/runbooks", { signal });
      if (!data) throw new Error("runbooks unavailable");
      return data.items;
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setQuery(draft.trim());
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <form role="search" onSubmit={submit} className="flex flex-1 gap-2">
          <label htmlFor="runbook-search" className="sr-only">
            Search runbooks
          </label>
          <Input
            id="runbook-search"
            type="search"
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              if (!e.target.value) setQuery("");
            }}
            placeholder="Describe the incident, e.g. checkout errors after a release"
            className="min-w-0 flex-1"
          />
          <Button type="submit" variant="secondary" disabled={draft.trim().length < 2}>
            Search
          </Button>
        </form>
        {canManage && <Button onClick={() => setCreating(true)}>New runbook</Button>}
      </div>

      {query ? (
        <SearchResults query={query} />
      ) : (
        <>
          {runbooks.isPending && <div aria-hidden className="h-40 skeleton rounded-card" />}
          {runbooks.isError && (
            <p role="alert" className="text-sm text-critical">
              Runbooks could not be loaded.
            </p>
          )}
          {runbooks.isSuccess && runbooks.data.length === 0 && (
            <p className="rounded-card border border-dashed border-border-strong p-10 text-center text-sm text-fg-muted">
              No runbooks yet.{canManage ? " Add one, or load the demo runbooks with make seed-runbooks." : ""}
            </p>
          )}
          {runbooks.isSuccess && runbooks.data.length > 0 && (
            <ul aria-label="Runbooks" className="surface-raised divide-y divide-border rounded-card border border-border">
              {runbooks.data.map((rb) => (
                <li key={rb.id} className="flex flex-col gap-1.5 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <Link href={`/runbooks/${rb.id}`} className="font-medium hover:text-accent">
                    {rb.title}
                  </Link>
                  <span className="flex flex-wrap items-center gap-3">
                    <Services slugs={rb.services} />
                    <span className="font-mono text-xs text-fg-muted">v{rb.version}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <Modal open={creating} title="New runbook" onClose={() => setCreating(false)}>
        <RunbookForm
          onSaved={(rb) => {
            setCreating(false);
            toast(`Runbook “${rb.title}” created`);
            void queryClient.invalidateQueries({ queryKey: RUNBOOKS_KEY });
            router.push(`/runbooks/${rb.id}`);
          }}
        />
      </Modal>
    </div>
  );
}
