"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";

type Finding = { statement: string; certainty: string; evidence: string[] };
type Content = {
  summary: string;
  impact: string;
  root_cause: Finding;
  findings: Finding[];
  resolution: string;
  follow_ups: string[];
  timeline: { at: string; event: string; actor: string }[];
  evidence: Record<string, { summary: string; source: string }>;
};

const CERTAINTY: Record<string, { label: string; className: string }> = {
  confirmed: { label: "Confirmed", className: "border-healthy/40 text-healthy" },
  strong_hypothesis: { label: "Strong hypothesis", className: "border-accent/40 text-accent" },
  weak_hypothesis: { label: "Weak hypothesis", className: "border-border-strong text-fg-secondary" },
  unknown: { label: "Unknown", className: "border-degraded/40 text-degraded" },
};

const time = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });

function Certainty({ value }: { value: string }) {
  const c = CERTAINTY[value] ?? CERTAINTY.unknown;
  return <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${c.className}`}>{c.label}</span>;
}

function FindingRow({ finding, evidence }: { finding: Finding; evidence: Content["evidence"] }) {
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm">{finding.statement}</p>
        <Certainty value={finding.certainty} />
      </div>
      {finding.evidence.length > 0 && (
        <p className="text-xs text-fg-muted">
          {finding.evidence.map((ref) => (
            <span key={ref} className="mr-3" title={evidence[ref]?.summary}>
              <span className="font-mono text-accent">{ref}</span> {evidence[ref]?.source}
            </span>
          ))}
        </p>
      )}
    </li>
  );
}

/** The drafted postmortem of a resolved incident, with certainty labels and citations. */
export function PostmortemView({ incidentId, canManage }: { incidentId: string; canManage: boolean }) {
  const key = ["postmortem", incidentId];
  const queryClient = useQueryClient();
  const toast = useToast();
  const postmortem = useQuery<components["schemas"]["PostmortemOut"] | null>({
    queryKey: key,
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 5000 : false),
    queryFn: async ({ signal }) => {
      const { data, response } = await createApiClient(window.location.origin).GET(
        "/api/v1/incidents/{incident_id}/postmortem",
        { params: { path: { incident_id: incidentId } }, signal },
      );
      if (response.status === 404) return null;
      if (!data) throw new Error("postmortem unavailable");
      return data;
    },
  });

  async function request() {
    const { data } = await createApiClient(window.location.origin).POST("/api/v1/incidents/{incident_id}/postmortem", {
      params: { path: { incident_id: incidentId } },
    });
    if (data) {
      queryClient.setQueryData(key, data);
      toast("Postmortem requested");
    } else toast("The postmortem could not be requested.", "error");
  }

  const pm = postmortem.data;
  const content = (pm?.status === "ready" ? pm.content : null) as Content | null;
  return (
    <Card as="section" aria-label="Postmortem" className="flex flex-col gap-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-medium text-fg-secondary">Postmortem</h2>
        {canManage && pm?.status !== "pending" && (
          <Button size="sm" variant="secondary" onClick={() => void request()}>
            {pm ? "Redraft" : "Draft postmortem"}
          </Button>
        )}
      </div>
      {postmortem.isPending && <div aria-hidden className="h-24 animate-pulse rounded-sm bg-surface-3" />}
      {postmortem.isSuccess && !pm && <p className="text-sm text-fg-muted">No postmortem drafted yet.</p>}
      {pm?.status === "pending" && (
        <p role="status" className="text-sm text-accent">
          Drafting the postmortem…
        </p>
      )}
      {content && (
        <>
          <p className="text-sm leading-relaxed">{content.summary}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <h3 className="text-xs text-fg-muted">Impact</h3>
              <p className="mt-1 text-sm">{content.impact}</p>
            </div>
            <div>
              <h3 className="text-xs text-fg-muted">Resolution</h3>
              <p className="mt-1 text-sm">{content.resolution}</p>
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-xs text-fg-muted">Root cause</h3>
            <ul>
              <FindingRow finding={content.root_cause} evidence={content.evidence} />
            </ul>
          </div>
          {content.findings.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs text-fg-muted">Findings</h3>
              <ul aria-label="Findings" className="flex flex-col gap-3">
                {content.findings.map((f) => (
                  <FindingRow key={f.statement} finding={f} evidence={content.evidence} />
                ))}
              </ul>
            </div>
          )}
          {content.follow_ups.length > 0 && (
            <div>
              <h3 className="text-xs text-fg-muted">Follow-ups</h3>
              <ul className="mt-1 list-disc pl-5 text-sm text-fg-secondary">
                {content.follow_ups.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </div>
          )}
          <details>
            <summary className="cursor-pointer text-xs text-fg-muted">Timeline ({content.timeline.length} events)</summary>
            <ol className="mt-2 flex flex-col gap-1 font-mono text-xs text-fg-secondary">
              {content.timeline.map((t) => (
                <li key={`${t.at}-${t.event}`}>
                  {time.format(new Date(t.at))} · {t.event} <span className="text-fg-muted">({t.actor})</span>
                </li>
              ))}
            </ol>
          </details>
          <p className="text-xs text-fg-muted">Drafted by {pm?.generated_by}; check every finding before publishing.</p>
        </>
      )}
    </Card>
  );
}
