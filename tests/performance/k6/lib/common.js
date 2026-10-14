// Shared pieces for the OpsPilot k6 scripts: configuration, dev-token
// handling, tagged requests, and the summary writer.
//
// Auth: pass TOKEN (e.g. TOKEN=$(make -s token USER=commander); it expires
// after five minutes), or let setup() log in to the local Keycloak dev realm
// (KEYCLOAK_URL, K6_USER) and the VUs refresh. Dev realm only.
import http from "k6/http";
import encoding from "k6/encoding";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.1.0/index.js";

export const BASE_URL = __ENV.API_URL || `http://127.0.0.1:${__ENV.API_PORT || "8000"}`;
export const API = `${BASE_URL}/api/v1`;
// The realm URL: KEYCLOAK_URL, else the API's JWT_ISSUER (from .env), else the compose default.
const KEYCLOAK_URL =
  __ENV.KEYCLOAK_URL || __ENV.JWT_ISSUER || `http://localhost:${__ENV.KEYCLOAK_PORT || "8080"}/realms/opspilot`;
const USER = __ENV.K6_USER || "commander";
// The dev realm's shared password (infrastructure/keycloak/realm-opspilot.json).
const DEV_PASSWORD = __ENV.K6_PASSWORD || "opspilot-dev";

// Plan §21.6 latency targets and the 1 % error budget.
export const TARGETS = {
  readP95: Number(__ENV.READ_P95_MS || 300),
  writeP95: Number(__ENV.WRITE_P95_MS || 500),
  errorRate: 0.01,
};

// One password login in setup() (Keycloak's brute-force protection rejects
// concurrent logins for the same user); VUs then renew the access token with
// the refresh token, each at a random point in the last 90 s before expiry.
let auth = null;
const refreshMargin = 30000 + Math.random() * 60000;

function claimsExpiry(accessToken) {
  return JSON.parse(encoding.b64decode(accessToken.split(".")[1], "rawurl", "s")).exp * 1000;
}

function tokenRequest(form) {
  const res = http.post(
    `${KEYCLOAK_URL}/protocol/openid-connect/token`,
    { client_id: "opspilot-dev-cli", ...form },
    { tags: { name: "keycloak token", kind: "auth" } },
  );
  if (res.status !== 200) throw new Error(`token request failed: HTTP ${res.status}`);
  return {
    access: res.json("access_token"),
    refresh: res.json("refresh_token"),
    expiresAt: claimsExpiry(res.json("access_token")),
  };
}

export function login() {
  if (__ENV.TOKEN) return { access: __ENV.TOKEN, refresh: null, expiresAt: claimsExpiry(__ENV.TOKEN) };
  return tokenRequest({ grant_type: "password", username: USER, password: DEV_PASSWORD });
}

export function bearer() {
  if (auth === null) throw new Error("call useAuth(data) first");
  if (auth.refresh && Date.now() > auth.expiresAt - refreshMargin) {
    auth = tokenRequest({ grant_type: "refresh_token", refresh_token: auth.refresh });
  }
  return `Bearer ${auth.access}`;
}

// Adopt the setup() login in this VU (once; later renewals stay per VU).
export function useAuth(data) {
  if (auth === null) auth = { ...data.auth };
}

function params(name, kind, extra = {}) {
  return {
    headers: { Authorization: bearer(), "Content-Type": "application/json", ...(extra.headers || {}) },
    tags: { name, kind },
    timeout: extra.timeout || "30s",
  };
}

export function get(path, name, kind = "read") {
  return http.get(`${API}${path}`, params(name, kind));
}

export function post(path, body, name, extra = {}) {
  return http.post(`${API}${path}`, JSON.stringify(body), params(name, "write", extra));
}

export function patch(path, body, name) {
  return http.patch(`${API}${path}`, JSON.stringify(body), params(name, "write"));
}

export const pick = (items) => items[Math.floor(Math.random() * items.length)];

// Catalogue and a sample of incident IDs, loaded once in setup().
export function loadFixtures() {
  const session = login();
  useAuth({ auth: session });
  const services = get("/services?limit=200", "setup").json("items");
  const incidents = get("/incidents?limit=200", "setup").json("items");
  if (!services.length || !incidents.length) {
    throw new Error("no data: run `make load-seed` (needs the demo services and incidents)");
  }
  return {
    auth: session,
    serviceIds: services.map((s) => s.id),
    incidentIds: incidents.map((i) => i.id),
  };
}

export function summary(name) {
  return (data) => ({
    stdout: textSummary(data, { indent: " ", enableColors: false }),
    [`test-results/k6/${name}.json`]: JSON.stringify(data, null, 2),
  });
}
