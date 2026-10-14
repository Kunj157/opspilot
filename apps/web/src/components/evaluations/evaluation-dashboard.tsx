"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { ActiveHighlight } from "@/components/motion/animated-background";
import { AnimatedNumber } from "@/components/motion/animated-number";
import { MotionScope } from "@/components/motion/motion-provider";
import { Card } from "@/components/ui/card";
import { SkeletonRows } from "@/components/ui/skeleton";
import { formatSeconds } from "@/lib/durations";

type Evaluations = components["schemas"]["Evaluations"];

export const RANGES = [7, 30, 90] as const;
export type RangeDays = (typeof RANGES)[number];

/** `?days=` → one of the offered ranges; anything else falls back to 30. */
export function parseRange(value: string | null): RangeDays {
  const days = Number(value);
  return (RANGES as readonly number[]).includes(days) ? (days as RangeDays) : 30;
}

const percent = (n: number) => `${Math.round(n * 100)}%`;
const usd = (n: number) => `$${n.toFixed(2)}`;
const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** Cost per investigation, or null when there were none. */
export function costPerInvestigation(data: Evaluations): number | null {
  return data.investigations.total ? data.agents.cost_usd / data.investigations.total : null;
}

function Metric({ label, value, format, hint }: { label: string; value: number | null; format?: (n: number) => string; hint?: string }) {
  return (
    <div role="group" aria-label={label} className="min-w-0">
      <p className="text-xs text-fg-secondary">{label}</p>
      <p className="mt-1.5 font-mono text-2xl font-semibold tracking-tight">
        {value === null ? "—" : <AnimatedNumber value={value} from={0} format={format} />}
      </p>
      {hint && <p className="mt-1 text-xs text-fg-muted">{hint}</p>}
    </div>
  );
}

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <Card as="section" aria-label={title} className="flex flex-col gap-5 p-5">
      <div>
        <h2 className="text-sm font-medium">{title}</h2>
        <p className="mt-1 text-xs text-fg-muted">{description}</p>
      </div>
      <div className="grid grid-cols-2 gap-5">{children}</div>
    </Card>
  );
}

const OUTCOMES = [
  { key: "succeeded", label: "Completed", bar: "bg-healthy", text: "text-healthy", glyph: "●" },
  { key: "partial", label: "Stopped early", bar: "bg-degraded", text: "text-degraded", glyph: "▲" },
  { key: "failed", label: "Failed", bar: "bg-critical", text: "text-critical", glyph: "■" },
] as const;

/** Investigation outcomes as one stacked bar with a labelled legend (never colour alone). */
function Outcomes({ data }: { data: Evaluations["investigations"] }) {
  const other = Math.max(0, data.total - data.succeeded - data.partial - data.failed);
  return (
    <div className="col-span-2 flex flex-col gap-3">
      <div aria-hidden className="flex h-2.5 overflow-hidden rounded-full bg-surface-3">
        {OUTCOMES.map((o) =>
          data[o.key] > 0 ? (
            <span key={o.key} className={`${o.bar} bar-grow-x`} style={{ width: `${(data[o.key] / Math.max(1, data.total)) * 100}%` }} />
          ) : null,
        )}
      </div>
      <ul aria-label="Investigation outcomes" className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-fg-secondary">
        {OUTCOMES.map((o) => (
          <li key={o.key} className="inline-flex items-center gap-1.5">
            <span aria-hidden className={`text-[0.7em] ${o.text}`}>
              {o.glyph}
            </span>
            {o.label} <span className="font-mono text-fg">{data[o.key]}</span>
          </li>
        ))}
        {other > 0 && (
          <li className="inline-flex items-center gap-1.5">
            In progress <span className="font-mono text-fg">{other}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

function RangePicker({ days, onChange }: { days: RangeDays; onChange: (days: RangeDays) => void }) {
  return (
    <MotionScope>
      <div role="group" aria-label="Time range" className="flex rounded-sm border border-border bg-surface-1 p-0.5">
        {RANGES.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={days === option}
            onClick={() => onChange(option)}
            className={`relative isolate rounded-[6px] px-3 py-1 font-mono text-xs transition-colors ${
              days === option ? "text-accent" : "text-fg-secondary hover:text-fg"
            }`}
          >
            {days === option && <ActiveHighlight layoutId="evaluation-range" className="rounded-[6px] bg-accent-subtle" />}
            {option}d
          </button>
        ))}
      </div>
    </MotionScope>
  );
}

/** How detection, the agents, and remediation performed over a time range. */
export function EvaluationDashboard() {
  const router = useRouter();
  const pathname = usePathname();
  const days = parseRange(useSearchParams().get("days"));

  const evaluations = useQuery({
    queryKey: ["evaluations", days],
    queryFn: async ({ signal }) => {
      const to = new Date();
      const from = new Date(to.getTime() - days * 86_400_000);
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/evaluations", {
        params: { query: { from: from.toISOString(), to: to.toISOString() } },
        signal,
      });
      if (!data) throw new Error("evaluations unavailable");
      return data;
    },
    placeholderData: (previous) => previous,
  });

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-fg-secondary">Last {days} days</p>
      <RangePicker days={days} onChange={(next) => router.replace(`${pathname}${next === 30 ? "" : `?days=${next}`}`, { scroll: false })} />
    </div>
  );

  if (evaluations.isPending) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <SkeletonRows rows={4} className="h-28" />
      </div>
    );
  }
  if (evaluations.isError) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <p role="alert" className="surface-raised rounded-card border border-border p-5 text-sm text-critical">
          Evaluation metrics could not be loaded.
        </p>
      </div>
    );
  }

  const data = evaluations.data;
  const toolAccuracy = data.agents.tool_error_rate === null ? null : 1 - data.agents.tool_error_rate;
  const investigationSuccess = data.investigations.total ? data.investigations.succeeded / data.investigations.total : null;
  return (
    <div className="flex flex-col gap-6">
      {header}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Agents" description="Model calls and the tools they used during investigations.">
          <Metric label="Agent success rate" value={data.agents.success_rate} format={percent} hint={`${data.agents.runs} runs`} />
          <Metric label="Tool-call accuracy" value={toolAccuracy} format={percent} hint={`${data.agents.tool_calls} tool calls`} />
        </Panel>
        <Panel title="Investigations" description="How agent investigations ended.">
          <Metric label="Investigation success rate" value={investigationSuccess} format={percent} hint={`${data.investigations.total} investigations`} />
          <Metric label="Cost per investigation" value={costPerInvestigation(data)} format={usd} hint="Estimated from token usage" />
          <Outcomes data={data.investigations} />
        </Panel>
        <Panel title="Detection" description="From the first anomalous window to the incident opening.">
          <Metric label="Detector incidents" value={data.detection.incidents} />
          <Metric label="Detection delay p50" value={data.detection.delay_p50_seconds} format={formatSeconds} hint={`p95 ${formatSeconds(data.detection.delay_p95_seconds)}`} />
        </Panel>
        <Panel title="Remediation and response" description="Human decisions on proposals, and time to acknowledge and resolve.">
          <Metric label="Approval rate" value={data.remediation.approval_rate} format={percent} hint={`${data.remediation.decisions} decisions`} />
          <Metric label="Mean time to resolve" value={data.response.mttr_seconds} format={formatSeconds} hint={`MTTA ${formatSeconds(data.response.mtta_seconds)}`} />
        </Panel>
      </div>
      <Card as="section" aria-label="Token usage" className="grid gap-5 p-5 sm:grid-cols-3">
        <Metric label="Input tokens" value={data.agents.input_tokens} format={(n) => compact.format(Math.round(n))} />
        <Metric label="Output tokens" value={data.agents.output_tokens} format={(n) => compact.format(Math.round(n))} />
        <Metric label="Estimated cost" value={data.agents.cost_usd} format={usd} />
      </Card>
      <p className="text-xs text-fg-muted">
        Computed live from incidents, investigations, agent runs, tool calls, and approvals. Retrieval relevance and
        groundedness are measured offline by the agent eval suite (<span className="font-mono">make test-agent</span>).
      </p>
    </div>
  );
}
