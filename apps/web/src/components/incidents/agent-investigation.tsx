"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";

type Investigation = components["schemas"]["InvestigationOut"];
type Evidence = components["schemas"]["EvidenceOut"];
type Proposal = components["schemas"]["ProposalOut"];
type AgentRun = components["schemas"]["AgentRunOut"];
type Hypothesis = { description: string; confidence: number; supporting_evidence: string[] };

export const investigationKeys = (incidentId: string) => ({
  all: ["investigation", incidentId] as const,
  investigation: ["investigation", incidentId, "latest"] as const,
  evidence: ["investigation", incidentId, "evidence"] as const,
  proposals: ["investigation", incidentId, "proposals"] as const,
  runs: ["investigation", incidentId, "runs"] as const,
});

const STATUS: Record<string, string> = {
  queued: "Queued",
  running: "Investigating",
  completed: "Complete",
  partial: "Stopped early",
  failed: "Failed",
};

const time = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });

function api() {
  return createApiClient(window.location.origin);
}

function useList<T>(key: readonly unknown[], path: "evidence" | "proposals" | "agent-runs", incidentId: string, live: boolean) {
  return useQuery({
    queryKey: key,
    refetchInterval: live ? 4000 : false,
    queryFn: async ({ signal }) => {
      const { data } = await api().GET(`/api/v1/incidents/{incident_id}/${path}` as "/api/v1/incidents/{incident_id}/evidence", {
        params: { path: { incident_id: incidentId } },
        signal,
      });
      if (!data) throw new Error(`${path} unavailable`);
      return data.items as T[];
    },
  });
}

function describeProposal(p: Proposal): string {
  const target = String(p.parameters.deployment ?? "the service");
  switch (p.action_type) {
    case "ROLLBACK_DEPLOYMENT":
      return `Roll back ${target} to revision ${String(p.parameters.to_revision)}`;
    case "RESTART_DEPLOYMENT":
      return `Restart ${target}`;
    case "SCALE_DEPLOYMENT":
      return `Scale ${target} to ${String(p.parameters.replicas)} replicas`;
    case "PAUSE_ROLLOUT":
      return `Pause the rollout of ${target}`;
    default:
      return "No action";
  }
}

function ProposalCard({ proposal, refs }: { proposal: Proposal; refs: Map<string, string> }) {
  const versions =
    proposal.parameters.from_version && proposal.parameters.to_version
      ? `${String(proposal.parameters.from_version)} → ${String(proposal.parameters.to_version)}`
      : null;
  return (
    <section aria-label="Proposed remediation" className="rounded-card border border-accent/40 bg-accent-subtle p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-accent">Proposed remediation</p>
      <p className="mt-2 font-medium">
        {describeProposal(proposal)}
        {versions && <span className="ml-2 font-mono text-sm text-fg-secondary">{versions}</span>}
      </p>
      <p className="mt-1 text-sm text-fg-secondary">{proposal.description}</p>
      <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-secondary">
        <span>{proposal.status === "PENDING" ? "Awaiting approval by an incident commander" : proposal.status.toLowerCase()}</span>
        <span>{proposal.risk_level} risk</span>
        <span>
          Cites{" "}
          {proposal.evidence_ids.map((id) => (
            <a key={id} href={`#evidence-${id}`} className="ml-1 font-mono text-accent hover:underline">
              {refs.get(id) ?? "evidence"}
            </a>
          ))}
        </span>
      </p>
    </section>
  );
}

function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (!evidence.length) return <p className="text-sm text-fg-muted">No evidence collected yet.</p>;
  return (
    <ol aria-label="Evidence" className="flex flex-col gap-2">
      {evidence.map((e, i) => (
        <li key={e.id} id={`evidence-${e.id}`} className="scroll-mt-24 rounded-sm border border-border bg-surface-1 p-3 target:border-accent">
          <p className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
            <span className="font-mono text-accent">E{i + 1}</span>
            <span className="rounded-sm bg-surface-3 px-1.5 py-0.5">{e.source}</span>
            {e.time_range_end && <time dateTime={e.time_range_end}>{time.format(new Date(e.time_range_end))}</time>}
            <span>{Math.round(e.confidence * 100)}% confidence</span>
          </p>
          <p className="mt-1.5 text-sm">{e.summary}</p>
          {e.query && <p className="mt-1 break-all font-mono text-[11px] text-fg-muted">{e.query}</p>}
        </li>
      ))}
    </ol>
  );
}

function ToolCalls({ runs }: { runs: AgentRun[] }) {
  const calls = runs.flatMap((r) => r.tool_calls.map((c) => ({ ...c, agent: r.agent_name })));
  if (!calls.length) return <p className="text-sm text-fg-muted">No tool calls yet.</p>;
  return (
    <ul aria-label="Tool calls" className="flex flex-col divide-y divide-border text-sm">
      {calls.map((c) => (
        <li key={c.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
          <span className="w-24 text-xs text-fg-muted">{c.agent}</span>
          <span className="font-mono text-xs">{c.tool_name}</span>
          <span className="font-mono text-[11px] text-fg-muted">{JSON.stringify(c.arguments)}</span>
          <span className={`ml-auto text-xs ${c.status === "succeeded" ? "text-fg-secondary" : "text-critical"}`}>
            {c.status === "succeeded" ? `${Math.round(c.duration_ms)} ms` : (c.error ?? "failed")}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The agents' findings for an incident: hypotheses, cited evidence, tool calls, proposal. */
export function AgentInvestigation({ incidentId, canInvestigate }: { incidentId: string; canInvestigate: boolean }) {
  const keys = investigationKeys(incidentId);
  const queryClient = useQueryClient();
  const toast = useToast();
  const [starting, setStarting] = useState(false);
  const investigation = useQuery<Investigation | null>({
    queryKey: keys.investigation,
    refetchInterval: (q) => (["queued", "running"].includes(q.state.data?.status ?? "") ? 4000 : false),
    queryFn: async ({ signal }) => {
      const { data, response } = await api().GET("/api/v1/incidents/{incident_id}/investigation", {
        params: { path: { incident_id: incidentId } },
        signal,
      });
      if (response.status === 404) return null;
      if (!data) throw new Error("investigation unavailable");
      return data;
    },
  });
  const live = ["queued", "running"].includes(investigation.data?.status ?? "");
  const evidence = useList<Evidence>(keys.evidence, "evidence", incidentId, live);
  const proposals = useList<Proposal>(keys.proposals, "proposals", incidentId, live);
  const runs = useList<AgentRun>(keys.runs, "agent-runs", incidentId, live);

  async function start() {
    setStarting(true);
    const { data } = await api().POST("/api/v1/incidents/{incident_id}/investigation", {
      params: { path: { incident_id: incidentId } },
    });
    setStarting(false);
    if (data) {
      queryClient.setQueryData(keys.investigation, data);
      toast("Investigation queued");
    } else toast("The investigation could not be started.", "error");
  }

  const inv = investigation.data;
  const result = (inv?.result ?? null) as { summary?: string; hypotheses?: Hypothesis[]; unknowns?: string[]; manual_review?: boolean; runbooks?: { title: string; version: number; runbook_id: string; score: number }[] } | null;
  const refs = new Map((evidence.data ?? []).map((e, i) => [e.id, `E${i + 1}`]));
  const byRef = new Map((evidence.data ?? []).map((e, i) => [`E${i + 1}`, e.id]));
  const proposal = proposals.data?.[0];
  const canStart = canInvestigate && !live;

  return (
    <Card as="section" aria-label="Agent investigation" className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-medium text-fg-secondary">Agent investigation</h2>
        <div className="flex items-center gap-3">
          {inv && (
            <span className={`inline-flex items-center gap-1.5 text-xs ${live ? "text-accent" : "text-fg-secondary"}`}>
              <span aria-hidden className={`size-1.5 rounded-full ${live ? "animate-pulse bg-accent" : "bg-fg-muted"}`} />
              {STATUS[inv.status] ?? inv.status}
              {inv.status === "running" && inv.current_node ? ` · ${inv.current_node}` : ""}
            </span>
          )}
          {canStart && (
            <Button size="sm" variant={inv ? "secondary" : "primary"} disabled={starting} onClick={() => void start()}>
              {inv ? "Run agents again" : "Run agent investigation"}
            </Button>
          )}
        </div>
      </div>

      {investigation.isPending && <div aria-hidden className="h-24 animate-pulse rounded-sm bg-surface-3" />}
      {investigation.isSuccess && !inv && (
        <p className="text-sm text-fg-muted">No agent has investigated this incident yet.</p>
      )}
      {inv && (inv.status === "partial" || inv.status === "failed") && (
        <p role="status" className="rounded-sm border border-degraded/40 px-3 py-2 text-sm text-degraded">
          ▲ Stopped early{inv.error ? `: ${inv.error}` : ""}. Evidence is kept; manual review recommended.
        </p>
      )}
      {result?.summary && <p className="text-sm leading-relaxed">{result.summary}</p>}

      {!!result?.hypotheses?.length && (
        <ul aria-label="Hypotheses" className="flex flex-col gap-2">
          {result.hypotheses.map((h) => (
            <li key={h.description} className="rounded-sm border border-border p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium">{h.description}</p>
                <span className="font-mono text-xs text-accent">{Math.round(h.confidence * 100)}%</span>
              </div>
              <div aria-hidden className="mt-2 h-1 rounded-full bg-surface-3">
                <div className="h-1 rounded-full bg-accent" style={{ width: `${Math.round(h.confidence * 100)}%` }} />
              </div>
              <p className="mt-2 text-xs text-fg-muted">
                Evidence:
                {h.supporting_evidence.map((ref) => (
                  <a key={ref} href={`#evidence-${byRef.get(ref) ?? ref}`} className="ml-1.5 font-mono text-accent hover:underline">
                    {ref}
                  </a>
                ))}
              </p>
            </li>
          ))}
        </ul>
      )}
      {!!result?.unknowns?.length && (
        <div>
          <p className="text-xs text-fg-muted">Unknown</p>
          <ul className="mt-1 list-disc pl-5 text-sm text-fg-secondary">
            {result.unknowns.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </div>
      )}

      {proposal && <ProposalCard proposal={proposal} refs={refs} />}

      {inv && (
        <Tabs
          label="Investigation details"
          items={[
            { id: "evidence", label: `Evidence (${evidence.data?.length ?? 0})`, content: <EvidenceList evidence={evidence.data ?? []} /> },
            { id: "tools", label: "Tool calls", content: <ToolCalls runs={runs.data ?? []} /> },
            {
              id: "runbooks",
              label: "Runbooks",
              content: result?.runbooks?.length ? (
                <ul className="flex flex-col gap-1 text-sm">
                  {result.runbooks.map((r) => (
                    <li key={r.runbook_id}>
                      <Link href={`/runbooks/${r.runbook_id}`} className="text-accent hover:underline">
                        {r.title} v{r.version}
                      </Link>
                      <span className="ml-2 font-mono text-xs text-fg-muted">{Math.round(r.score * 100)}% match</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-fg-muted">No runbook retrieved.</p>
              ),
            },
          ]}
        />
      )}
      {inv && (
        <p className="text-xs text-fg-muted">
          {inv.tool_calls} tool calls · {inv.input_tokens + inv.output_tokens} tokens
          {inv.cost_usd > 0 ? ` · $${inv.cost_usd.toFixed(3)}` : ""}
        </p>
      )}
    </Card>
  );
}
