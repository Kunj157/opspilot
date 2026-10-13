import { describe, expect, it } from "vitest";

import { formatSeconds } from "./durations";

describe("formatSeconds", () => {
  it.each([
    [null, "—"],
    [0, "<1m"],
    [59, "<1m"],
    [60, "1m"],
    [6 * 60 + 30, "6m"],
    [3600 + 12 * 60, "1h 12m"],
    [2 * 86400 + 3 * 3600 + 59, "2d 3h"],
  ])("%s seconds reads %s", (seconds, text) => {
    expect(formatSeconds(seconds)).toBe(text);
  });
});
