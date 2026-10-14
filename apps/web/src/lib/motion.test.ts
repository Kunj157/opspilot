import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { duration, ease, STAGGER_CAP, staggerDelay } from "./motion";

const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");
function token(name: string): string | undefined {
  const start = css.indexOf(`--${name}:`);
  if (start < 0) return undefined;
  return css.slice(start + name.length + 3, css.indexOf(";", start)).trim();
}

describe("motion tokens", () => {
  it.each(Object.entries(duration))("duration.%s mirrors the CSS token", (name, seconds) => {
    expect(token(`duration-${name}`)).toBe(`${Math.round(seconds * 1000)}ms`);
  });

  it.each([
    ["out", "ease-out"],
    ["inOut", "ease-in-out"],
  ] as const)("ease.%s mirrors --%s", (name, css) => {
    expect(token(css)).toBe(`cubic-bezier(${ease[name].join(", ")})`);
  });

  it("caps the list stagger", () => {
    expect(staggerDelay(0)).toBe(0);
    expect(staggerDelay(2)).toBeCloseTo(0.06);
    expect(staggerDelay(100)).toBe(staggerDelay(STAGGER_CAP));
  });
});
