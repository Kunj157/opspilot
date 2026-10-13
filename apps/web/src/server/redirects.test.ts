import { describe, expect, it } from "vitest";

import { safeReturnTo } from "./redirects";

describe("safeReturnTo", () => {
  it.each([
    ["/", "/"],
    ["/incidents", "/incidents"],
    ["/incidents/42?tab=logs#t", "/incidents/42?tab=logs#t"],
  ])("keeps same-site path %s", (input, expected) => {
    expect(safeReturnTo(input)).toBe(expected);
  });

  it.each([
    null,
    undefined,
    "",
    "https://evil.example/",
    "//evil.example/path",
    "/\\evil.example",
    "\\\\evil.example",
    "javascript:alert(1)",
    "incidents",
  ])("falls back to / for %s", (input) => {
    expect(safeReturnTo(input)).toBe("/");
  });

  it("keeps an encoded double slash as a harmless same-site path", () => {
    // The browser resolves this against our origin; it never leaves the site.
    expect(safeReturnTo("/%2F%2Fevil.example")).toBe("/%2F%2Fevil.example");
  });
});
