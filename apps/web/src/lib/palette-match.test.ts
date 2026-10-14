import { describe, expect, it } from "vitest";

import { filterItems, score } from "./palette-match";

const items = [
  { id: "1", group: "Go to", label: "Runbook index" },
  { id: "2", group: "Go to", label: "Incidents" },
  { id: "3", group: "Go to", label: "System status" },
  { id: "4", group: "Incidents", label: "Checkout latency", keywords: "payments critical" },
];

describe("score", () => {
  it("requires every character in order", () => {
    expect(score("inc", "Incidents")).toBeGreaterThan(0);
    expect(score("cni", "Incidents")).toBe(0);
  });

  it("prefers prefixes and word starts", () => {
    expect(score("st", "System status")).toBeGreaterThan(0);
    expect(score("in", "Incidents")).toBeGreaterThan(score("in", "Runbook index"));
  });

  it("matches everything for an empty query", () => {
    expect(score("  ", "Anything")).toBe(1);
  });
});

describe("filterItems", () => {
  it("ranks the best match first and drops misses", () => {
    expect(filterItems(items, "in").map((i) => i.id)).toEqual(["2", "1"]);
  });

  it("matches hidden keywords", () => {
    expect(filterItems(items, "payments").map((i) => i.id)).toEqual(["4"]);
  });

  it("returns everything in order without a query", () => {
    expect(filterItems(items, "")).toBe(items);
  });
});
