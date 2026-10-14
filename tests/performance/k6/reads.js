// Authenticated read endpoints at a constant arrival rate.
// Target (plan §21.6): p95 < 300 ms, errors < 1 %.
import { check } from "k6";
import { TARGETS, get, loadFixtures, pick, summary, useAuth } from "./lib/common.js";

const RATE = Number(__ENV.READ_RATE || 50);
const DURATION = __ENV.DURATION || "2m";
const QUERIES = ["checkout errors after deploy", "database connections exhausted", "pod crash loop", "payment timeout"];

const READ_NAMES = [
  "GET /incidents",
  "GET /incidents/{id}",
  "GET /incidents/{id}/events",
  "GET /services",
  "GET /topology",
  "GET /incident-metrics",
  "GET /audit-logs",
  "GET /runbooks/search",
];

export const options = {
  scenarios: {
    reads: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: Math.max(10, RATE),
      maxVUs: RATE * 4,
    },
  },
  thresholds: {
    "http_req_duration{kind:read}": [`p(95)<${TARGETS.readP95}`],
    "http_req_failed{kind:read}": [`rate<${TARGETS.errorRate}`],
    checks: ["rate>0.99"],
    // Per endpoint, so the summary breaks latency down by route.
    ...Object.fromEntries(READ_NAMES.map((name) => [`http_req_duration{name:${name}}`, [`p(95)<${TARGETS.readP95}`]])),
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export const setup = loadFixtures;

// Weighted like the UI: lists and detail pages dominate.
const READS = [
  [30, () => get("/incidents?limit=50", "GET /incidents")],
  [25, (f) => get(`/incidents/${pick(f.incidentIds)}`, "GET /incidents/{id}")],
  [15, (f) => get(`/incidents/${pick(f.incidentIds)}/events`, "GET /incidents/{id}/events")],
  [10, () => get("/services", "GET /services")],
  [5, () => get("/topology", "GET /topology")],
  [5, () => get("/incident-metrics", "GET /incident-metrics")],
  [5, () => get("/audit-logs?limit=50", "GET /audit-logs")],
  [5, () => get(`/runbooks/search?q=${encodeURIComponent(pick(QUERIES))}`, "GET /runbooks/search")],
];
const TOTAL = READS.reduce((sum, [weight]) => sum + weight, 0);

export function read(fixtures) {
  useAuth(fixtures);
  let roll = Math.random() * TOTAL;
  for (const [weight, request] of READS) {
    roll -= weight;
    if (roll < 0) {
      const res = request(fixtures);
      check(res, { "read ok": (r) => r.status === 200 });
      return;
    }
  }
}

export default read;
export const handleSummary = summary("reads");
