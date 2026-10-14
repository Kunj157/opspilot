// Mutations at a constant arrival rate: incident creation bursts, transitions,
// edits, and agent-job submissions (queued, never waiting for the model).
// Every mutation also writes audit records. Target: p95 < 500 ms, errors < 1 %.
import { check } from "k6";
import { uuidv4 } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";
import { TARGETS, loadFixtures, patch, pick, post, summary, useAuth } from "./lib/common.js";

const RATE = Number(__ENV.WRITE_RATE || 5);
const DURATION = __ENV.DURATION || "2m";

export const options = {
  scenarios: {
    writes: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: Math.max(10, RATE * 4),
      maxVUs: RATE * 20,
    },
  },
  thresholds: {
    "http_req_duration{kind:write}": [`p(95)<${TARGETS.writeP95}`],
    "http_req_failed{kind:write}": [`rate<${TARGETS.errorRate}`],
    checks: ["rate>0.99"],
    ...Object.fromEntries(
      [
        "POST /incidents",
        "POST /incidents/{id}/acknowledge",
        "PATCH /incidents/{id}",
        "POST /incidents/{id}/investigation",
      ].map((name) => [`http_req_duration{name:${name}}`, [`p(95)<${TARGETS.writeP95}`]]),
    ),
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export const setup = loadFixtures;

// One incident's life: create, acknowledge, edit, queue an investigation.
export function write(data) {
  useAuth(data);
  const { serviceIds } = data;
  const created = post(
    "/incidents",
    { title: "k6 burst incident", severity: pick(["high", "medium"]), service_id: pick(serviceIds) },
    "POST /incidents",
    { headers: { "Idempotency-Key": uuidv4() } },
  );
  if (!check(created, { "incident created": (r) => r.status === 201 })) return;
  const id = created.json("id");
  const ack = post(
    `/incidents/${id}/acknowledge`,
    { version: created.json("version") },
    "POST /incidents/{id}/acknowledge",
  );
  if (!check(ack, { acknowledged: (r) => r.status === 200 })) return;
  const edited = patch(
    `/incidents/${id}`,
    { version: ack.json("version"), description: "Updated by k6." },
    "PATCH /incidents/{id}",
  );
  check(edited, { edited: (r) => r.status === 200 });
  const job = post(`/incidents/${id}/investigation`, {}, "POST /incidents/{id}/investigation");
  check(job, { "investigation queued": (r) => r.status === 202 || r.status === 200 });
}

export default write;
export const handleSummary = summary("writes");
