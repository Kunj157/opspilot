"use client";

import { createApiClient } from "@opspilot/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { MarkdownLite } from "@/lib/markdown-lite";

import { RUNBOOKS_KEY } from "./runbook-library";
import { RunbookForm } from "./runbook-form";

export function RunbookDetail({ canManage }: { canManage: boolean }) {
  const { runbookId } = useParams<{ runbookId: string }>();
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();
  const toast = useToast();
  const key = ["runbook", runbookId];
  const runbook = useQuery({
    queryKey: key,
    queryFn: async ({ signal }) => {
      const { data, response } = await createApiClient(window.location.origin).GET("/api/v1/runbooks/{runbook_id}", {
        params: { path: { runbook_id: runbookId } },
        signal,
      });
      if (response.status === 404 || response.status === 422) return null;
      if (!data) throw new Error("runbook unavailable");
      return data;
    },
  });

  if (runbook.isPending) return <div aria-hidden className="h-64 skeleton rounded-card" />;
  if (runbook.isError)
    return (
      <p role="alert" className="text-sm text-critical">
        This runbook could not be loaded.
      </p>
    );
  if (!runbook.data)
    return (
      <Card className="p-8 text-center">
        <p className="font-medium">Runbook not found</p>
        <Link href="/runbooks" className="mt-2 inline-block text-sm text-accent hover:underline">
          Back to runbooks
        </Link>
      </Card>
    );

  const rb = runbook.data;
  async function archive() {
    const { data } = await createApiClient(window.location.origin).POST("/api/v1/runbooks/{runbook_id}/archive", {
      params: { path: { runbook_id: rb.id } },
    });
    if (data) {
      queryClient.setQueryData(key, data);
      void queryClient.invalidateQueries({ queryKey: RUNBOOKS_KEY });
      toast(`Runbook “${rb.title}” archived`);
    } else toast("The runbook could not be archived.", "error");
  }

  return (
    <article className="flex flex-col gap-8">
      <header className="flex flex-col gap-4">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{rb.title}</h1>
        <dl className="grid grid-cols-2 gap-5 surface-raised rounded-card border border-border p-5 lg:grid-cols-4">
          <div>
            <dt className="text-xs text-fg-muted">Version</dt>
            <dd className="mt-1 font-mono text-sm">v{rb.version}</dd>
          </div>
          <div>
            <dt className="text-xs text-fg-muted">Status</dt>
            <dd className="mt-1 text-sm capitalize">{rb.status}</dd>
          </div>
          <div>
            <dt className="text-xs text-fg-muted">Services</dt>
            <dd className="mt-1 font-mono text-sm">{rb.services.join(", ") || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-fg-muted">Owner</dt>
            <dd className="mt-1 text-sm">{rb.owner ?? "—"}</dd>
          </div>
        </dl>
        <div className="flex flex-wrap items-center gap-3">
          {canManage && <Button onClick={() => setEditing(true)}>Edit runbook</Button>}
          {canManage && rb.status === "active" && (
            <Button variant="secondary" onClick={() => void archive()}>
              Archive
            </Button>
          )}
          {rb.source_url && (
            <a href={rb.source_url} target="_blank" rel="noreferrer" className="text-sm text-accent hover:underline">
              Source ↗
            </a>
          )}
        </div>
      </header>

      {rb.sections.map((section) => (
        <section key={section.heading} aria-labelledby={`s-${section.heading}`}>
          <h2 id={`s-${section.heading}`} className="mb-3 text-lg font-medium">
            {section.heading}
          </h2>
          <MarkdownLite text={section.body} />
        </section>
      ))}

      <Modal open={editing} title="Edit runbook" onClose={() => setEditing(false)}>
        <RunbookForm
          runbook={rb}
          onSaved={(saved) => {
            setEditing(false);
            queryClient.setQueryData(key, saved);
            void queryClient.invalidateQueries({ queryKey: RUNBOOKS_KEY });
            toast(saved.version === rb.version ? "No changes to save" : `Saved version ${saved.version}`);
          }}
        />
      </Modal>
    </article>
  );
}
