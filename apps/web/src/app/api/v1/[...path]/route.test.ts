// @vitest-environment node
/**
 * The API proxy's trust boundary: CSRF origin check on state-changing
 * requests, and no path that escapes /api/v1.
 */
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE, GET, POST } from "./route";

vi.mock("server-only", () => ({}));
vi.mock("@/server/config", () => ({
  serverConfig: () => ({ apiUrl: "http://backend.test:8000", trustedProxyHops: 0, production: false }),
}));
vi.mock("@/server/oidc", () => ({ accessTokenFor: async () => "session-token" }));
vi.mock("@/server/sessions", () => ({ SESSION_COOKIE: "opspilot_session" }));

const ORIGIN = "https://ops.example";
let upstream: ReturnType<typeof vi.fn>;

beforeEach(() => {
  upstream = vi.fn(async () => Response.json({ ok: true }));
  vi.stubGlobal("fetch", upstream);
});
afterEach(() => vi.unstubAllGlobals());

function call(
  handler: typeof GET,
  path: string[],
  { method = "POST", headers = {} }: { method?: string; headers?: Record<string, string> } = {},
) {
  const request = new NextRequest(`${ORIGIN}/api/v1/${path.join("/")}`, {
    method,
    headers: { "content-type": "application/json", ...headers },
    body: method === "GET" ? undefined : "{}",
  });
  return handler(request, { params: Promise.resolve({ path }) });
}

describe("CSRF origin check", () => {
  it.each([
    ["a foreign Origin", { origin: "https://evil.example" }],
    ["a look-alike Origin", { origin: "https://ops.example.evil.example" }],
    ["an opaque Origin", { origin: "null" }],
    ["no Origin from another site", { "sec-fetch-site": "cross-site" }],
    ["no Origin from a sibling subdomain", { "sec-fetch-site": "same-site" }],
    ["no Origin and no fetch metadata", {}],
  ])("rejects a mutation with %s", async (_, headers) => {
    for (const handler of [POST, DELETE]) {
      const response = await call(handler, ["incidents"], { method: handler === POST ? "POST" : "DELETE", headers });

      expect(response.status).toBe(403);
    }
    expect(upstream).not.toHaveBeenCalled();
  });

  it.each([
    ["its own Origin", { origin: ORIGIN }],
    ["same-origin fetch metadata", { "sec-fetch-site": "same-origin" }],
  ])("forwards a mutation with %s, using the session token", async (_, headers) => {
    const response = await call(POST, ["incidents"], { headers });

    expect(response.status).toBe(200);
    const [target, init] = upstream.mock.calls[0] as [URL, RequestInit];
    expect(String(target)).toBe("http://backend.test:8000/api/v1/incidents");
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer session-token");
  });

  it("lets reads through (they change nothing)", async () => {
    const response = await call(GET, ["incidents"], { method: "GET", headers: { origin: "https://evil.example" } });

    expect(response.status).toBe(200);
  });
});

describe("path confinement", () => {
  it.each([[["..", "..", "metrics"]], [["incidents", "..", "..", "..", "metrics"]], [["."]]])(
    "refuses %j without calling the API",
    async (path) => {
      const response = await call(GET, path, { method: "GET" });

      expect(response.status).toBe(404);
      expect(upstream).not.toHaveBeenCalled();
    },
  );

  it("keeps encoded separators inside one segment", async () => {
    await call(GET, ["incidents", "a/../../metrics"], { method: "GET" });

    expect(String(upstream.mock.calls[0][0])).toBe("http://backend.test:8000/api/v1/incidents/a%2F..%2F..%2Fmetrics");
  });
});
