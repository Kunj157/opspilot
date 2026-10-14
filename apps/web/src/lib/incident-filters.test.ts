import { describe, expect, it } from "vitest";

import { ACTIVE_STATUSES, filtersToSearch, parseFilters, toApiQuery } from "./incident-filters";

describe("incident filters", () => {
  it("defaults to active incidents of any severity", () => {
    const filters = parseFilters(new URLSearchParams());

    expect(filters).toEqual({
      status: "active",
      severity: [],
      service: null,
      source: null,
      since: null,
      until: null,
      assignee: null,
    });
    expect(toApiQuery(filters, "me")).toEqual({ status: ACTIVE_STATUSES });
  });

  it("round-trips every filter through the URL", () => {
    const filters = {
      status: "RESOLVED" as const,
      severity: ["critical" as const, "high" as const],
      service: "00000000-0000-4000-8000-000000000001",
      source: "detector" as const,
      since: "2026-10-01",
      until: "2026-10-13",
      assignee: "me",
    };

    expect(parseFilters(new URLSearchParams(filtersToSearch(filters)))).toEqual(filters);
    const someone = { ...filters, assignee: "00000000-0000-4000-8000-0000000000aa" };
    expect(parseFilters(new URLSearchParams(filtersToSearch(someone)))).toEqual(someone);
  });

  it("filters by any assignee and keeps ?mine=1 links working", () => {
    expect(parseFilters(new URLSearchParams("mine=1")).assignee).toBe("me");
    expect(parseFilters(new URLSearchParams("assignee=not-a-uuid")).assignee).toBeNull();
    const other = "00000000-0000-4000-8000-0000000000aa";
    expect(toApiQuery({ ...parseFilters(new URLSearchParams(`assignee=${other}`)) }, "user-1").assigned_user_id).toBe(other);
  });

  it("drops values the API would reject instead of failing the page", () => {
    const filters = parseFilters(
      new URLSearchParams("status=NOPE&severity=bad&severity=low&source=x&since=yesterday&service=<script>"),
    );

    expect(filters.status).toBe("active");
    expect(filters.severity).toEqual(["low"]);
    expect(filters.source).toBeNull();
    expect(filters.since).toBeNull();
    expect(filters.service).toBeNull();
  });

  it("omits defaults from the URL so the plain page stays clean", () => {
    expect(filtersToSearch(parseFilters(new URLSearchParams()))).toBe("");
    expect(filtersToSearch({ ...parseFilters(new URLSearchParams()), status: "all" })).toBe("?status=all");
  });

  it("maps filters to the API query, with whole-day date bounds", () => {
    const query = toApiQuery(
      {
        status: "all",
        severity: ["medium"],
        service: "svc",
        source: "manual",
        since: "2026-10-01",
        until: "2026-10-02",
        assignee: "me",
      },
      "user-1",
    );

    expect(query).toEqual({
      severity: ["medium"],
      service_id: "svc",
      source: "manual",
      since: new Date(2026, 9, 1).toISOString(),
      until: new Date(2026, 9, 3).toISOString(),
      assigned_user_id: "user-1",
    });
  });
});
