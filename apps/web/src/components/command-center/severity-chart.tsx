"use client";

import { useState } from "react";

type Day = { date: string; critical: number; high: number; medium: number; low: number };
type Severity = "critical" | "high" | "medium" | "low";

// Bottom to top. Critical sits on the baseline in its status colour; the rest
// are neutral steps, so the one colour on the chart means "critical".
const SERIES: { key: Severity; label: string; className: string }[] = [
  { key: "critical", label: "Critical", className: "fill-critical" },
  { key: "high", label: "High", className: "fill-chart-1" },
  { key: "medium", label: "Medium", className: "fill-chart-2" },
  { key: "low", label: "Low", className: "fill-chart-3" },
];
const SWATCH: Record<Severity, string> = {
  critical: "bg-critical",
  high: "bg-chart-1",
  medium: "bg-chart-2",
  low: "bg-chart-3",
};

const HEIGHT = 160;
const TOP = 8;
const BOTTOM = 22;
const LEFT = 28;
const SLOT = 30;
const BAR = 18;
const GAP = 2;
const RADIUS = 4;

const dayLabel = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
const format = (iso: string) => dayLabel.format(new Date(`${iso}T00:00:00Z`));
const total = (d: Day) => d.critical + d.high + d.medium + d.low;

/** Smallest clean axis maximum (multiples of 2, 5, or 10) at or above `value`. */
export function niceMax(value: number): number {
  if (value <= 4) return 4;
  const step = value <= 12 ? 2 : value <= 20 ? 5 : 10;
  return Math.ceil(value / step) * step;
}

/** Column with a 4px rounded top and a square base. */
function topRounded(x: number, y: number, w: number, h: number) {
  const r = Math.min(RADIUS, h, w / 2);
  return `M${x} ${y + h}V${y + r}Q${x} ${y} ${x + r} ${y}H${x + w - r}Q${x + w} ${y} ${x + w} ${y + r}V${y + h}Z`;
}

function Table({ daily }: { daily: Day[] }) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-fg-muted">
        <tr>
          <th className="py-1 font-normal">Day</th>
          {SERIES.map((s) => (
            <th key={s.key} className="py-1 text-right font-normal">
              {s.label}
            </th>
          ))}
          <th className="py-1 text-right font-normal">Total</th>
        </tr>
      </thead>
      <tbody className="font-mono text-fg-secondary">
        {daily.map((d) => (
          <tr key={d.date} className="border-t border-border">
            <td className="py-1 font-sans">{format(d.date)}</td>
            {SERIES.map((s) => (
              <td key={s.key} className="py-1 text-right">
                {d[s.key]}
              </td>
            ))}
            <td className="py-1 text-right text-fg">{total(d)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Incidents started per day, stacked by severity, with a table view. */
export function SeverityChart({ daily }: { daily: Day[] }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [table, setTable] = useState(false);
  const max = niceMax(Math.max(0, ...daily.map(total)));
  const plot = HEIGHT - TOP - BOTTOM;
  const width = LEFT + daily.length * SLOT;
  const y = (n: number) => TOP + plot - (n / max) * plot;
  const labelEvery = Math.ceil(daily.length / 7);
  const active = daily.find((d) => d.date === hovered);
  const activeIndex = daily.findIndex((d) => d.date === hovered);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ul aria-label="Legend" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-secondary">
          {SERIES.map((s) => (
            <li key={s.key} className="inline-flex items-center gap-1.5">
              <span aria-hidden className={`size-2 rounded-[2px] ${SWATCH[s.key]}`} />
              {s.label}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => setTable((t) => !t)}
          className="text-xs text-fg-secondary underline-offset-2 hover:text-fg hover:underline"
        >
          {table ? "Show chart" : "Show table"}
        </button>
      </div>
      {table ? (
        <Table daily={daily} />
      ) : (
        <div className="relative">
          <svg
            role="img"
            aria-label={`Incidents started per day by severity, last ${daily.length} days`}
            viewBox={`0 0 ${width} ${HEIGHT}`}
            className="h-auto w-full overflow-visible"
          >
            {[0, max / 2, max].map((tick) => (
              <g key={tick}>
                <line x1={LEFT} x2={width} y1={y(tick)} y2={y(tick)} className="stroke-border" strokeWidth={1} />
                <text x={LEFT - 6} y={y(tick) + 3} textAnchor="end" className="fill-fg-muted font-mono text-[9px]">
                  {tick}
                </text>
              </g>
            ))}
            {daily.map((d, i) => {
              const x = LEFT + i * SLOT + (SLOT - BAR) / 2;
              const present = SERIES.filter((s) => d[s.key] > 0);
              let base = y(0);
              return (
                <g key={d.date} data-day={d.date} opacity={hovered && hovered !== d.date ? 0.55 : 1}>
                  {present.map((s, index) => {
                    const height = (d[s.key] / max) * plot - (index < present.length - 1 ? GAP : 0);
                    const top = base - height;
                    const last = index === present.length - 1;
                    const segment = last ? (
                      <path key={s.key} data-severity={s.key} d={topRounded(x, top, BAR, height)} className={s.className} />
                    ) : (
                      <rect key={s.key} data-severity={s.key} x={x} y={top} width={BAR} height={height} className={s.className} />
                    );
                    base = top - GAP;
                    return segment;
                  })}
                  {i % labelEvery === 0 && (
                    <text x={x + BAR / 2} y={HEIGHT - 6} textAnchor="middle" className="fill-fg-muted text-[9px]">
                      {format(d.date)}
                    </text>
                  )}
                  <rect
                    data-hit
                    x={LEFT + i * SLOT}
                    y={TOP}
                    width={SLOT}
                    height={plot}
                    fill="transparent"
                    onPointerEnter={() => setHovered(d.date)}
                    onPointerLeave={() => setHovered(null)}
                  />
                </g>
              );
            })}
          </svg>
          {active && (
            <div
              role="tooltip"
              className="pointer-events-none absolute top-0 z-10 w-36 rounded-sm border border-border bg-surface-3 px-3 py-2 text-xs shadow-3"
              style={{
                left: `${((LEFT + activeIndex * SLOT + SLOT / 2) / width) * 100}%`,
                transform: activeIndex > daily.length / 2 ? "translateX(-105%)" : "translateX(5%)",
              }}
            >
              <p className="font-medium text-fg">{format(active.date)}</p>
              <p className="mb-1 text-fg-muted">
                {total(active)} incident{total(active) === 1 ? "" : "s"}
              </p>
              {SERIES.map((s) => (
                <p key={s.key} className="flex items-center justify-between gap-2 text-fg-secondary">
                  <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden className={`size-2 rounded-[2px] ${SWATCH[s.key]}`} />
                    {s.label}
                  </span>
                  <span className="font-mono text-fg">{active[s.key]}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
