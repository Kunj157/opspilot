"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export type Proposal = components["schemas"]["ProposalOut"];

const time = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });

export function describeProposal(p: Proposal): string {
  const target = String(p.parameters.deployment ?? "the service");
  switch (p.action_type) {
    case "ROLLBACK_DEPLOYMENT":
      return `Roll back ${target} to revision ${String(p.parameters.to_revision)}`;
    case "RESTART_DEPLOYMENT":
      return `Restart ${target}`;
    case "SCALE_DEPLOYMENT":
      return `Scale ${target} to ${String(p.parameters.replicas)} replicas`;
    default:
      return "No action";
  }
}

/** True while the proposal is approved but not yet executed and verified. */
export function inFlight(p: Proposal | undefined): boolean {
  if (!p) return false;
  return ["APPROVED", "EXECUTING"].includes(p.status) || p.execution?.verification_status === "pending";
}

function verificationPlan(plan: Record<string, unknown>): string {
  const parts = [];
  if (typeof plan.max_error_rate === "number") parts.push(`error rate ≤ ${Math.round(plan.max_error_rate * 100)}%`);
  if (typeof plan.max_p95_ratio_to_baseline === "number") parts.push(`p95 ≤ ${plan.max_p95_ratio_to_baseline}× baseline`);
  const window = typeof plan.window_minutes === "number" ? ` over ${plan.window_minutes} min` : "";
  return parts.length ? `Then verify ${parts.join(", ")}${window} after the rollout.` : "";
}

function expiry(expiresAt: string | null | undefined, now: number): string | null {
  if (!expiresAt) return null;
  const minutes = Math.round((new Date(expiresAt).getTime() - now) / 60_000);
  return minutes <= 0 ? "Expired" : `Expires in ${minutes} min`;
}

type Step = { label: string; detail?: string | null; at?: string | null; state: "done" | "active" | "failed" };

function steps(p: Proposal): Step[] {
  const out: Step[] = [{ label: "Proposed by the remediation agent", at: p.created_at, state: "done" }];
  const d = p.decision;
  if (d) {
    out.push({
      label: `${d.decision === "approved" ? "Approved" : "Rejected"} by ${d.reviewer_name}`,
      detail: d.comment,
      at: d.reviewed_at,
      state: d.decision === "approved" ? "done" : "failed",
    });
  }
  const e = p.execution;
  if (d?.decision === "approved" && !e) out.push({ label: "Executing…", state: "active" });
  if (e) {
    if (e.status === "running") out.push({ label: "Executing…", detail: e.attempts > 1 ? `attempt ${e.attempts}` : null, state: "active" });
    if (e.status === "failed") out.push({ label: "Execution failed", detail: e.error_message, at: e.completed_at, state: "failed" });
    if (e.status === "succeeded") {
      const version = typeof e.output.version === "string" ? ` (${e.output.version})` : "";
      out.push({ label: `Executed${version}`, at: e.completed_at, state: "done" });
      const reason = typeof e.verification.reason === "string" ? e.verification.reason : null;
      if (e.verification_status === "pending") out.push({ label: "Verifying recovery…", detail: "waiting for the rollout and one verification window", state: "active" });
      if (e.verification_status === "passed") out.push({ label: "Recovery verified", detail: reason, at: e.verified_at, state: "done" });
      if (e.verification_status === "failed") out.push({ label: "Verification failed; investigating again", detail: reason, at: e.verified_at, state: "failed" });
    }
  }
  return out;
}

const DOT: Record<Step["state"], string> = {
  done: "bg-healthy",
  active: "animate-pulse bg-accent",
  failed: "bg-critical",
};

function Progress({ proposal }: { proposal: Proposal }) {
  return (
    <ol aria-label="Remediation progress" className="mt-3 flex flex-col gap-2 border-t border-accent/20 pt-3">
      {steps(proposal).map((s) => (
        <li key={s.label} className="flex items-start gap-2 text-sm">
          <span aria-hidden className={`mt-1.5 size-1.5 shrink-0 rounded-full ${DOT[s.state]}`} />
          <span className="flex-1">
            <span className={s.state === "failed" ? "text-critical" : undefined}>{s.label}</span>
            {s.detail && <span className="block text-xs text-fg-secondary">{s.detail}</span>}
          </span>
          {s.at && (
            <time dateTime={s.at} className="text-xs text-fg-muted">
              {time.format(new Date(s.at))}
            </time>
          )}
        </li>
      ))}
    </ol>
  );
}

/**
 * The proposed remediation with its evidence, verification plan, and progress.
 * Approvers decide on the exact version shown; the API enforces who may.
 */
export function RemediationReview({
  proposal,
  refs,
  canApprove,
  now,
  onDecided,
}: {
  proposal: Proposal;
  refs: Map<string, string>;
  canApprove: boolean;
  now: number;
  onDecided: () => void;
}) {
  const toast = useToast();
  const commentId = useId();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const versions =
    proposal.parameters.from_version && proposal.parameters.to_version
      ? `${String(proposal.parameters.from_version)} → ${String(proposal.parameters.to_version)}`
      : null;
  const expires = expiry(proposal.expires_at, now);
  const pending = proposal.status === "PENDING" && expires !== "Expired";

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    const path = decision === "approve" ? "/api/v1/proposals/{proposal_id}/approve" : "/api/v1/proposals/{proposal_id}/reject";
    const { data, error } = await createApiClient(window.location.origin).POST(path, {
      params: { path: { proposal_id: proposal.id } },
      body: { version: proposal.version, comment: comment.trim() || null },
    });
    setBusy(false);
    if (data) toast(decision === "approve" ? "Approved: the worker runs it now" : "Proposal rejected");
    else toast((error as { detail?: string } | undefined)?.detail ?? "The decision could not be recorded.", "error");
    onDecided();
  }

  return (
    <section aria-label="Proposed remediation" className="rounded-card border border-accent/40 bg-accent-subtle p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-accent">Proposed remediation</p>
      <p className="mt-2 font-medium">
        {describeProposal(proposal)}
        {versions && <span className="ml-2 font-mono text-sm text-fg-secondary">{versions}</span>}
      </p>
      <p className="mt-1 text-sm text-fg-secondary">{proposal.description}</p>
      <p className="mt-2 text-xs text-fg-secondary">{verificationPlan(proposal.verification_plan)}</p>
      <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-secondary">
        <span>
          {pending
            ? canApprove
              ? "Awaiting your decision"
              : "Awaiting approval by an incident commander"
            : proposal.status === "PENDING" || proposal.status === "EXPIRED"
              ? "Expired; run the agents again for a fresh proposal"
              : proposal.status.toLowerCase()}
        </span>
        <span>{proposal.risk_level} risk</span>
        {pending && expires && <span>{expires}</span>}
        <span>
          Cites{" "}
          {proposal.evidence_ids.map((id) => (
            <a key={id} href={`#evidence-${id}`} className="ml-1 font-mono text-accent hover:underline">
              {refs.get(id) ?? "evidence"}
            </a>
          ))}
        </span>
      </p>

      {pending && canApprove && (
        <div className="mt-4 flex flex-col gap-2">
          <label htmlFor={commentId} className="text-xs text-fg-secondary">
            Comment (recorded with your decision)
          </label>
          <textarea
            id={commentId}
            rows={2}
            maxLength={1000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="w-full rounded-sm border border-border bg-surface-1 px-2.5 py-2 text-sm placeholder:text-fg-muted focus:border-accent focus:outline-none"
          />
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => void decide("approve")}>
              Approve and run
            </Button>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void decide("reject")}>
              Reject
            </Button>
          </div>
        </div>
      )}

      {proposal.status !== "PENDING" && <Progress proposal={proposal} />}
    </section>
  );
}
