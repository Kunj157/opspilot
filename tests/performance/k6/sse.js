// Live incident stream under load: SSE_CLIENTS concurrent subscribers to the
// organization stream while a writer keeps changing incidents. Each client
// listens, disconnects, and reconnects with Last-Event-ID, then checks against
// the stored timeline that nothing was lost or delivered twice.
//
// Needs the xk6-sse community extension, which k6 resolves automatically with
// K6_ENABLE_COMMUNITY_EXTENSIONS=true (`make test-load` sets it).
import { check } from "k6";
import sse from "k6/x/sse";
import { Counter, Rate, Trend } from "k6/metrics";
import { API, bearer, get, loadFixtures, summary, useAuth } from "./lib/common.js";
import { write } from "./writes.js";

const CLIENTS = Number(__ENV.SSE_CLIENTS || 50);
const SESSION_MS = Number(__ENV.SSE_SESSION_SECONDS || 20) * 1000;
const DURATION = __ENV.DURATION || "2m";

const connectTime = new Trend("sse_connect_ms", true);
const deliveryLag = new Trend("sse_delivery_lag_ms", true);
const received = new Counter("sse_events_received");
const missed = new Counter("sse_events_missed");
const duplicates = new Counter("sse_events_duplicated");
const reconnected = new Rate("sse_reconnect_ok");

export const options = {
  scenarios: {
    writer: {
      executor: "constant-arrival-rate",
      exec: "writer",
      rate: 2,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: 10,
      maxVUs: 40,
    },
    listeners: { executor: "constant-vus", exec: "listen", vus: CLIENTS, duration: DURATION },
  },
  thresholds: {
    sse_events_missed: ["count==0"],
    sse_events_duplicated: ["count==0"],
    sse_reconnect_ok: ["rate>0.99"],
    sse_connect_ms: ["p(95)<1000"],
    sse_delivery_lag_ms: ["p(95)<2000"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export const setup = loadFixtures;
export const writer = write;

// One subscription; returns the last event ID seen.
function session(lastEventId, seen) {
  const started = Date.now();
  let last = lastEventId;
  const headers = { Authorization: bearer(), Accept: "text/event-stream" };
  if (lastEventId) headers["Last-Event-ID"] = String(lastEventId);
  const res = sse.open(
    `${API}/incidents/stream`,
    { method: "GET", headers, tags: { name: "GET /incidents/stream" } },
    (client) => {
      client.on("open", () => connectTime.add(Date.now() - started));
      client.on("event", (event) => {
        if (event.id) {
          const sequence = Number(event.id);
          if (seen.has(sequence) || (last && sequence <= last)) duplicates.add(1);
          seen.set(sequence, JSON.parse(event.data).incident.id);
          last = Math.max(last || 0, sequence);
          received.add(1);
          deliveryLag.add(Date.now() - Date.parse(JSON.parse(event.data).created_at));
        }
        if (Date.now() - started > SESSION_MS) client.close();
      });
      client.on("error", () => client.close());
    },
  );
  return { ok: res && res.status === 200, last };
}

export function listen(data) {
  useAuth(data);
  const seen = new Map();
  const first = session(null, seen);
  if (!check(first, { "stream opened": (r) => r.ok })) return;
  const second = session(first.last, seen);
  reconnected.add(second.ok);
  if (!second.ok || seen.size === 0) return;

  // Every stored event inside the window, for a few incidents we saw, must have arrived.
  const sequences = [...seen.keys()];
  const low = Math.min(...sequences);
  const high = Math.max(...sequences);
  const incidents = [...new Set(seen.values())].slice(0, 3);
  for (const incidentId of incidents) {
    const timeline = get(`/incidents/${incidentId}/events`, "GET /incidents/{id}/events", "verify").json("items");
    for (const event of timeline) {
      if (event.sequence >= low && event.sequence <= high && !seen.has(event.sequence)) missed.add(1);
    }
  }
}

export const handleSummary = summary("sse");
