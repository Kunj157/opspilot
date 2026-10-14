import { describe, expect, it } from "vitest";

import { trail } from "./breadcrumbs";

describe("trail", () => {
  it("names the section on list pages", () => {
    expect(trail("/")).toEqual([{ label: "Command center" }]);
    expect(trail("/incidents")).toEqual([{ label: "Incidents" }]);
  });

  it("links back to the section from detail pages", () => {
    expect(trail("/services/abc")).toEqual([{ label: "Services", href: "/services" }, { label: "Service" }]);
  });

  it("returns nothing for unknown paths", () => {
    expect(trail("/nowhere")).toEqual([]);
  });
});
