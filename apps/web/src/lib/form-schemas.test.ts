import { describe, expect, it } from "vitest";

import { incidentSchema, runbookSchema, serverFieldErrors, serviceSchema } from "./form-schemas";

const service = { name: "Checkout", slug: "checkout", description: "", owner_team: "", repository_url: "", namespace: "", deployment_name: "" };

describe("form schemas", () => {
  it("requires an incident title and trims it", () => {
    expect(incidentSchema.safeParse({ title: "  ", severity: "high", service_id: "", description: "" }).success).toBe(false);
    expect(incidentSchema.parse({ title: " Latency ", severity: "high", service_id: "", description: "" }).title).toBe("Latency");
  });

  it("accepts blank optional service fields and mirrors the API's patterns", () => {
    expect(serviceSchema.safeParse(service).success).toBe(true);
    const bad = serviceSchema.safeParse({ ...service, slug: "Check Out", namespace: "Not_Valid", repository_url: "ftp://x" });
    expect(bad.success).toBe(false);
    const paths = bad.error!.issues.map((issue) => issue.path[0]);
    expect(paths).toEqual(expect.arrayContaining(["slug", "namespace", "repository_url"]));
  });

  it("asks for runbook front matter", () => {
    expect(runbookSchema.safeParse({ content: "# no front matter" }).success).toBe(false);
    expect(runbookSchema.safeParse({ content: "---\ntitle: x\n---\n# Steps" }).success).toBe(true);
  });

  it("maps API validation errors onto known fields", () => {
    const body = { detail: [{ loc: ["body", "slug"], msg: "taken" }, { loc: ["body", "other"], msg: "nope" }] };
    expect(serverFieldErrors(body, ["slug"] as const)).toEqual({ fields: { slug: "taken" }, form: "nope" });
    expect(serverFieldErrors({ detail: "x" }, ["slug"] as const)).toEqual({ fields: {} });
  });
});
