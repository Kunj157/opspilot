"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";

type Model = components["schemas"]["ModelOut"];
type Metrics = Record<string, number | null | undefined>;

const KEY = ["ml"] as const;
const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** Rows of the comparison: label, metric key, formatter, and which direction is better. */
const ROWS: { label: string; key: string; format: (v: number) => string; better: "higher" | "lower" }[] = [
  { label: "Precision", key: "precision", format: (v) => v.toFixed(2), better: "higher" },
  { label: "Recall", key: "recall", format: (v) => v.toFixed(2), better: "higher" },
  { label: "F1", key: "f1", format: (v) => v.toFixed(2), better: "higher" },
  { label: "False alerts per hour", key: "false_alerts_per_hour", format: (v) => v.toFixed(2), better: "lower" },
  { label: "Median detection delay", key: "median_detection_delay_s", format: (v) => `${Math.round(v)} s`, better: "lower" },
  { label: "P95 detection delay", key: "p95_detection_delay_s", format: (v) => `${Math.round(v)} s`, better: "lower" },
  { label: "Missed incidents", key: "missed_incidents", format: (v) => String(v), better: "lower" },
  { label: "Inference per window", key: "inference_ms_per_window", format: (v) => `${v.toFixed(2)} ms`, better: "lower" },
];

function api() {
  return createApiClient(window.location.origin);
}

function winner(row: (typeof ROWS)[number], baseline: Metrics, model: Metrics): "baseline" | "model" | null {
  const b = baseline[row.key];
  const m = model[row.key];
  if (b == null || m == null || b === m) return null;
  return (row.better === "higher" ? m > b : m < b) ? "model" : "baseline";
}

function Cell({ value, format, best }: { value: number | null | undefined; format: (v: number) => string; best: boolean }) {
  return (
    <td className={`px-3 py-2 text-right font-mono tabular-nums ${best ? "font-semibold text-fg" : "text-fg-secondary"}`}>
      {value == null ? "—" : format(value)}
      {best && <span className="sr-only"> (better)</span>}
      {best && (
        <span aria-hidden className="ml-1.5 text-accent">
          ●
        </span>
      )}
    </td>
  );
}

function Comparison({ model }: { model: Model }) {
  const metrics = model.metrics as { model?: Metrics; baseline?: Metrics; promotable?: boolean; reason?: string; test?: { runs?: number[]; scenarios?: string[] } };
  const m = metrics.model ?? {};
  const b = metrics.baseline ?? {};
  return (
    <div className="flex flex-col gap-3">
      <table aria-label="Detector comparison" className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-fg-muted">
            <th scope="col" className="px-3 py-2 text-left font-medium">
              Held-out runs
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Rolling z-score (baseline)
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Isolation Forest
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {ROWS.map((row) => {
            const best = winner(row, b, m);
            return (
              <tr key={row.key}>
                <th scope="row" className="px-3 py-2 text-left font-normal">
                  {row.label}
                </th>
                <Cell value={b[row.key]} format={row.format} best={best === "baseline"} />
                <Cell value={m[row.key]} format={row.format} best={best === "model"} />
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-xs text-fg-muted">
        <span aria-hidden className="text-accent">
          ●
        </span>{" "}
        better of the two. Tested on {metrics.test?.runs?.length ?? 0} failure runs held out in time
        {metrics.test?.scenarios?.length ? ` (${metrics.test.scenarios.join(", ")})` : ""}.
      </p>
      <p role="status" className={`text-sm ${metrics.promotable ? "text-healthy" : "text-degraded"}`}>
        {metrics.promotable ? "✓ Meets the promotion rule" : "▲ Does not meet the promotion rule"}
        {metrics.reason ? `: ${metrics.reason}` : ""}
      </p>
    </div>
  );
}

type Shadow = components["schemas"]["ShadowSummary"];

function ShadowTable({ shadow }: { shadow: Shadow }) {
  if (!shadow.model) return <p className="text-sm text-fg-muted">No model is running in shadow mode.</p>;
  return (
    <table aria-label="Shadow predictions by service" className="w-full text-sm">
      <thead>
        <tr className="border-b border-border text-xs text-fg-muted">
          <th scope="col" className="px-3 py-2 text-left font-medium">
            Service
          </th>
          <th scope="col" className="px-3 py-2 text-right font-medium">
            Windows scored
          </th>
          <th scope="col" className="px-3 py-2 text-right font-medium">
            Model alerts
          </th>
          <th scope="col" className="px-3 py-2 text-right font-medium">
            Rule triggers
          </th>
          <th scope="col" className="px-3 py-2 text-right font-medium">
            Incidents
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {shadow.services.map((s) => (
          <tr key={s.service_id}>
            <th scope="row" className="px-3 py-2 text-left font-normal">
              {s.service}
            </th>
            <td className="px-3 py-2 text-right font-mono tabular-nums text-fg-secondary">{s.shadow_windows}</td>
            <td className="px-3 py-2 text-right font-mono tabular-nums">{s.shadow_alerts}</td>
            <td className="px-3 py-2 text-right font-mono tabular-nums">{s.rule_triggers}</td>
            <td className="px-3 py-2 text-right font-mono tabular-nums">{s.incidents}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Model versions, the held-out comparison with the baseline, and live shadow results. */
export function ModelComparison({ canManage }: { canManage: boolean }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const models = useQuery({
    queryKey: [...KEY, "models"],
    queryFn: async ({ signal }) => {
      const { data } = await api().GET("/api/v1/ml/models", { signal });
      if (!data) throw new Error("models unavailable");
      return data.items;
    },
  });
  const shadow = useQuery({
    queryKey: [...KEY, "shadow"],
    refetchInterval: 30_000,
    queryFn: async ({ signal }) => {
      const { data } = await api().GET("/api/v1/ml/shadow", { params: { query: { hours: 24 } }, signal });
      if (!data) throw new Error("shadow results unavailable");
      return data;
    },
  });

  async function promoteModel(model: Model) {
    setBusy(model.id);
    const { data, error } = await api().POST("/api/v1/ml/models/{model_id}/promote", {
      params: { path: { model_id: model.id } },
    });
    setBusy(null);
    if (data) toast(`${model.name} v${model.version} now runs in shadow mode`);
    else toast((error as { detail?: string } | undefined)?.detail ?? "The model could not be promoted.", "error");
    void queryClient.invalidateQueries({ queryKey: KEY });
  }

  if (models.isPending) return <div aria-hidden className="h-64 animate-pulse rounded-card bg-surface-2" />;
  if (models.isError)
    return (
      <p role="alert" className="rounded-card border border-border bg-surface-2 p-5 text-sm text-critical">
        Models could not be loaded.
      </p>
    );
  const items = models.data;
  const current = items.find((m) => m.status === "shadow") ?? items[0];
  if (!current)
    return (
      <Card className="p-8 text-center">
        <p className="font-medium">No model registered yet</p>
        <p className="mt-2 text-sm text-fg-secondary">
          Train one with <code className="font-mono">make ml-train</code>, then register its report with{" "}
          <code className="font-mono">python -m opspilot_api.ml register</code>.
        </p>
      </Card>
    );

  return (
    <div className="flex flex-col gap-6">
      <Card as="section" aria-label="Held-out evaluation" className="flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-medium text-fg-secondary">
            {current.name} v{current.version} against the baseline
          </h2>
          <span className="text-xs text-fg-muted">
            Feature schema {String(current.feature_schema.version)} ·{" "}
            {(current.feature_schema.features as string[] | undefined)?.length ?? 0} features
          </span>
        </div>
        <Comparison model={current} />
      </Card>

      <Card as="section" aria-label="Shadow mode" className="flex flex-col gap-3 p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-medium text-fg-secondary">Shadow mode, last 24 hours</h2>
          <span className="text-xs text-fg-muted">The model only observes; the error-rate rule still decides.</span>
        </div>
        {shadow.data ? <ShadowTable shadow={shadow.data} /> : <div aria-hidden className="h-24 animate-pulse rounded-sm bg-surface-3" />}
      </Card>

      <Card as="section" aria-label="Model versions" className="flex flex-col gap-3 p-5">
        <h2 className="text-sm font-medium text-fg-secondary">Versions</h2>
        <ul className="flex flex-col divide-y divide-border">
          {items.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-sm">
              <span className="font-mono">
                {m.name} v{m.version}
              </span>
              <span className={`rounded-full border px-2 py-0.5 text-[11px] ${m.status === "shadow" ? "border-accent/50 text-accent" : "border-border text-fg-secondary"}`}>
                {m.status}
              </span>
              <span className="text-xs text-fg-muted">registered {date.format(new Date(m.created_at))}</span>
              {canManage && m.status !== "shadow" && (
                <Button size="sm" variant="secondary" className="ml-auto" disabled={busy === m.id} onClick={() => void promoteModel(m)}>
                  {m.status === "retired" ? "Roll back to this version" : "Run in shadow mode"}
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
