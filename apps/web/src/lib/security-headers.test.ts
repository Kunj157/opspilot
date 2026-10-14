import { describe, expect, it } from "vitest";

import nextConfig from "../../next.config";
import { contentSecurityPolicy, securityHeaders } from "./security-headers";

function directives(policy: string): Map<string, string[]> {
  return new Map(
    policy.split(";").map((d) => {
      const [name, ...sources] = d.trim().split(/\s+/);
      return [name, sources];
    }),
  );
}

describe("content security policy", () => {
  const production = directives(contentSecurityPolicy({ dev: false }));

  it("never allows eval in production", () => {
    expect(production.get("script-src")).not.toContain("'unsafe-eval'");
    expect(directives(contentSecurityPolicy({ dev: true })).get("script-src")).toContain("'unsafe-eval'");
  });

  it("limits scripts, connections, and workers to this origin", () => {
    expect(production.get("default-src")).toEqual(["'self'"]);
    expect(production.get("script-src")).toEqual(["'self'", "'unsafe-inline'"]);
    expect(production.get("connect-src")).toEqual(["'self'"]);
    expect(production.get("worker-src")).toEqual(["'self'", "blob:"]);
  });

  it("blocks plugins, framing, and base rewriting", () => {
    expect(production.get("object-src")).toEqual(["'none'"]);
    expect(production.get("frame-ancestors")).toEqual(["'none'"]);
    expect(production.get("base-uri")).toEqual(["'self'"]);
  });

  it("allows no wildcard or foreign source", () => {
    for (const sources of production.values()) {
      for (const source of sources) expect(source).toMatch(/^('[a-z-]+'|data:|blob:)$/);
    }
  });
});

describe("security headers", () => {
  const headers = new Map(securityHeaders({ dev: false }).map((h) => [h.key, h.value]));

  it("sets the hardening headers", () => {
    expect(headers.get("Strict-Transport-Security")).toBe("max-age=63072000; includeSubDomains");
    expect(headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(headers.get("X-Frame-Options")).toBe("DENY");
    expect(headers.get("Referrer-Policy")).toBe("strict-origin-when-cross-origin");
    expect(headers.get("Cross-Origin-Opener-Policy")).toBe("same-origin");
    expect(headers.get("Permissions-Policy")).toContain("camera=()");
    expect(headers.get("Permissions-Policy")).toContain("microphone=()");
  });

  it("is applied to every path by next.config", async () => {
    const rules = await nextConfig.headers!();

    expect(rules).toHaveLength(1);
    expect(rules[0].source).toBe("/:path*");
    expect(rules[0].headers.map((h) => h.key)).toContain("Content-Security-Policy");
    expect(nextConfig.poweredByHeader).toBe(false);
  });
});
