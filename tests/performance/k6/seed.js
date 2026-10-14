// Seed incidents for the load tests: SEED_INCIDENTS (default 500) spread over
// the demo services, a third acknowledged so lists and timelines have depth.
// Needs the demo services: `make seed` first.
import { check } from "k6";
import { uuidv4 } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";
import { get, login, pick, post, useAuth } from "./lib/common.js";

const COUNT = Number(__ENV.SEED_INCIDENTS || 500);
const SEVERITIES = ["critical", "high", "medium", "low"];

export const options = {
  scenarios: {
    seed: { executor: "shared-iterations", vus: Math.min(10, COUNT), iterations: COUNT, maxDuration: "10m" },
  },
  thresholds: { checks: ["rate>0.99"] },
};

export function setup() {
  const session = login();
  useAuth({ auth: session });
  const services = get("/services?limit=200", "setup").json("items");
  if (!services.length) throw new Error("no services: run `make seed` first");
  return { auth: session, serviceIds: services.map((s) => s.id) };
}

export default function (data) {
  useAuth(data);
  const { serviceIds } = data;
  const res = post(
    "/incidents",
    {
      title: `Load-test seed incident ${__ITER}`,
      description: "Seeded for the k6 load tests.",
      severity: pick(SEVERITIES),
      service_id: pick(serviceIds),
    },
    "POST /incidents",
    { headers: { "Idempotency-Key": uuidv4() } },
  );
  check(res, { "incident created": (r) => r.status === 201 });
  if (res.status === 201 && Math.random() < 0.33) {
    const ack = post(
      `/incidents/${res.json("id")}/acknowledge`,
      { version: res.json("version") },
      "POST /incidents/{id}/acknowledge",
    );
    check(ack, { "incident acknowledged": (r) => r.status === 200 });
  }
}
