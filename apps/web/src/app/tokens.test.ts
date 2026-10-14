import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// Every text and status token meets WCAG AA (4.5:1) on every surface.
const css = readFileSync(join(__dirname, "globals.css"), "utf8");
const root = css.slice(css.indexOf(":root {"), css.indexOf("}", css.indexOf(":root {")));
const tokens = Object.fromEntries(
  [...root.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6});/gi)].map(([, name, hex]) => [name, hex]),
);

const fills = Object.fromEntries(
  [...root.matchAll(/--([\w-]+):\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\);/gi)].map(
    ([, name, r, g, b, a]) => [name, [Number(r), Number(g), Number(b), Number(a)] as const],
  ),
);

/** A translucent fill composited over an opaque surface, as hex. */
function over(fill: readonly [number, number, number, number], surface: string): string {
  const [r, g, b, a] = fill;
  return `#${[r, g, b]
    .map((c, i) => {
      const base = parseInt(surface.slice(1 + i * 2, 3 + i * 2), 16);
      return Math.round(c * a + base * (1 - a))
        .toString(16)
        .padStart(2, "0");
    })
    .join("")}`;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const SURFACES = ["background", "surface-1", "surface-2", "surface-3"];
const FOREGROUNDS = [
  "text-primary",
  "text-secondary",
  "text-muted",
  "accent",
  "status-healthy",
  "status-degraded",
  "status-critical",
  "status-unknown",
];

describe("Graphite & Iris tokens", () => {
  it("defines every surface and foreground token as hex", () => {
    for (const name of [...SURFACES, ...FOREGROUNDS, "on-accent", "accent-hover"]) {
      expect(tokens[name], name).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it.each(FOREGROUNDS.flatMap((fg) => SURFACES.map((bg) => [fg, bg])))(
    "%s on %s meets WCAG AA",
    (fg, bg) => {
      expect(contrast(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(4.5);
    },
  );

  it.each(["accent", "accent-hover"])("on-accent text is readable on %s", (bg) => {
    expect(contrast(tokens["on-accent"], tokens[bg])).toBeGreaterThanOrEqual(4.5);
  });

  // Badges and selected items put full-strength text on a subtle fill of the same hue.
  const TINTED: [string, string][] = [
    ["status-healthy", "status-healthy-subtle"],
    ["status-degraded", "status-degraded-subtle"],
    ["status-critical", "status-critical-subtle"],
    ["accent", "accent-subtle"],
    ["text-primary", "accent-subtle"],
  ];
  it.each(TINTED.flatMap(([fg, fill]) => SURFACES.map((bg) => [fg, fill, bg])))(
    "%s on %s over %s meets WCAG AA",
    (fg, fill, bg) => {
      expect(fills[fill], fill).toBeDefined();
      expect(contrast(tokens[fg], over(fills[fill], tokens[bg]))).toBeGreaterThanOrEqual(4.5);
    },
  );

  it("composites translucent fills", () => {
    expect(over([255, 255, 255, 0.5], "#000000")).toBe("#808080");
  });

  it("computes known ratios", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
  });
});
