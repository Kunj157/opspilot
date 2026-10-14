// Sustained mixed load: reads and writes at the UI's ratio plus open live
// streams, for DURATION (default 10 minutes). Same targets as the focused runs.
import sse from "k6/x/sse";
import { TARGETS, API, bearer, loadFixtures, summary, useAuth } from "./lib/common.js";
import { read } from "./reads.js";
import { write } from "./writes.js";

const DURATION = __ENV.DURATION || "10m";

export const options = {
  scenarios: {
    reads: {
      executor: "constant-arrival-rate",
      exec: "reader",
      rate: Number(__ENV.READ_RATE || 40),
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: 40,
      maxVUs: 200,
    },
    writes: {
      executor: "constant-arrival-rate",
      exec: "writer",
      rate: Number(__ENV.WRITE_RATE || 2),
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: 10,
      maxVUs: 60,
    },
    streams: { executor: "constant-vus", exec: "stream", vus: Number(__ENV.SSE_CLIENTS || 25), duration: DURATION },
  },
  thresholds: {
    "http_req_duration{kind:read}": [`p(95)<${TARGETS.readP95}`],
    "http_req_duration{kind:write}": [`p(95)<${TARGETS.writeP95}`],
    "http_req_failed{kind:read}": [`rate<${TARGETS.errorRate}`],
    "http_req_failed{kind:write}": [`rate<${TARGETS.errorRate}`],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export const setup = loadFixtures;
export const reader = read;
export const writer = write;

// A browser tab with the incident list open: one stream, reopened every minute.
export function stream(data) {
  useAuth(data);
  const started = Date.now();
  sse.open(
    `${API}/incidents/stream`,
    { method: "GET", headers: { Authorization: bearer() }, tags: { name: "GET /incidents/stream" } },
    (client) => {
      client.on("event", () => {
        if (Date.now() - started > 60000) client.close();
      });
      client.on("error", () => client.close());
    },
  );
}

export const handleSummary = summary("mixed");
