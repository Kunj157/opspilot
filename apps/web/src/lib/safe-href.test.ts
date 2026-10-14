import { describe, expect, it } from "vitest";

import { safeHref } from "./safe-href";

describe("safeHref", () => {
  it.each(["https://git.example/a.md", "http://wiki.example/page?x=1#y"])("keeps %s", (url) => {
    expect(safeHref(url)).toBe(url);
  });

  it.each([
    "javascript:alert(1)",
    " JavaScript:alert(1)",
    "java\tscript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "//evil.example/x",
    "/relative/path",
    "not a url",
    "",
    null,
    undefined,
  ])("drops %s", (url) => {
    expect(safeHref(url)).toBeNull();
  });
});
