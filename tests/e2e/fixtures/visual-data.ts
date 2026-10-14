/**
 * Fixed API responses for the visual snapshots: a small, believable shop so
 * every page shows real states (critical, degraded, investigating, resolved)
 * and the pixels do not depend on whatever other specs created.
 */

export const NOW = new Date("2026-10-14T09:30:00Z");

const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const minutesAgo = (m: number) => new Date(NOW.getTime() - m * 60_000).toISOString();

const SERVICES = [
  { n: 1, name: "Storefront", slug: "storefront", health: "healthy", team: "web" },
  { n: 2, name: "Checkout", slug: "checkout", health: "critical", team: "payments" },
  { n: 3, name: "Payments", slug: "payments", health: "degraded", team: "payments" },
  { n: 4, name: "Inventory", slug: "inventory", health: "healthy", team: "fulfilment" },
  { n: 5, name: "Search", slug: "search", health: "healthy", team: "discovery" },
  { n: 6, name: "Notifications", slug: "notifications", health: "unknown", team: "platform" },
] as const;

export const services = {
  items: SERVICES.map((s) => ({
    id: id(100 + s.n),
    name: s.name,
    slug: s.slug,
    description: `${s.name} service for the demo shop.`,
    owner_team: s.team,
    repository_url: null,
    namespace: "demo",
    deployment_name: s.slug,
    health_status: s.health,
    created_at: "2026-10-01T08:00:00Z",
    updated_at: "2026-10-14T08:00:00Z",
  })),
};

const EDGES: [number, number][] = [
  [1, 2],
  [1, 5],
  [2, 3],
  [2, 4],
  [2, 6],
  [3, 6],
];

export const topology = {
  nodes: SERVICES.map((s) => ({
    id: id(100 + s.n),
    name: s.name,
    slug: s.slug,
    health_status: s.health,
    active_incidents: s.n === 2 ? 2 : s.n === 3 ? 1 : 0,
    investigating: s.n === 2,
  })),
  edges: EDGES.map(([a, b]) => ({ source_id: id(100 + a), target_id: id(100 + b) })),
};

const INCIDENTS = [
  { n: 1, title: "Checkout error rate above 5%", severity: "critical", status: "INVESTIGATING", service: 2, source: "detector", ago: 18 },
  { n: 2, title: "Payment authorisation latency p95 over 2s", severity: "high", status: "AWAITING_APPROVAL", service: 3, source: "detector", ago: 42 },
  { n: 3, title: "Checkout pods restarting after release 2026.10.14", severity: "critical", status: "REMEDIATING", service: 2, source: "alertmanager", ago: 65 },
  { n: 4, title: "Search results stale for some categories", severity: "medium", status: "DETECTED", service: 5, source: "manual", ago: 120 },
  { n: 5, title: "Notification e-mails delayed", severity: "low", status: "MONITORING", service: 6, source: "manual", ago: 240 },
] as const;

export const incidents = {
  items: INCIDENTS.map((i) => ({
    id: id(i.n),
    title: i.title,
    description: null,
    severity: i.severity,
    status: i.status,
    source: i.source,
    service_id: id(100 + i.service),
    started_at: minutesAgo(i.ago),
    acknowledged_at: i.status === "DETECTED" ? null : minutesAgo(i.ago - 3),
    resolved_at: null,
    detection_score: i.source === "detector" ? 0.92 : null,
    assigned_user_id: null,
    version: 2,
    created_at: minutesAgo(i.ago),
    updated_at: minutesAgo(i.ago - 3),
    allowed_transitions: [],
  })),
  next_cursor: null,
};

export const metrics = {
  window_days: 30,
  mtta_seconds: 4 * 60 + 12,
  mttr_seconds: 52 * 60,
  acknowledged: 21,
  resolved: 18,
  active_by_severity: { critical: 2, high: 1, medium: 1, low: 1 },
  daily: Array.from({ length: 30 }, (_, d) => {
    const date = new Date(Date.UTC(2026, 8, 15 + d)).toISOString().slice(0, 10);
    const wave = (k: number) => Math.max(0, Math.round(1.5 + Math.sin((d + k) / 2.3) * 1.6));
    return { date, critical: d % 6 === 0 ? 1 : 0, high: wave(1) % 3, medium: wave(3), low: wave(5) % 2 };
  }),
};

export const runbooks = {
  items: [
    ["Checkout high error rate", ["checkout"], "payments", 3],
    ["Payment provider timeouts", ["payments"], "payments", 2],
    ["Deployment rollback", ["checkout", "payments", "storefront"], "platform", 5],
    ["Database connection exhaustion", ["inventory"], "fulfilment", 1],
  ].map(([title, svc, owner, version], n) => ({
    id: id(200 + n),
    slug: String(title).toLowerCase().replace(/ /g, "-"),
    title,
    services: svc,
    owner,
    version,
    status: "active",
    source_url: null,
    updated_at: minutesAgo(60 * 24 * (n + 1)),
  })),
};

const model = (version: number, status: string) => ({
  id: id(300 + version),
  name: "isolation-forest",
  version,
  status,
  feature_schema: { version: "v1", features: ["request_rate", "error_rate"] },
  metrics: {
    test: { runs: [5, 6], scenarios: ["checkout-http-500", "checkout-latency"] },
    model: { f1: 0.87, recall: 0.84, precision: 0.91, missed_incidents: 0, false_alerts_per_hour: 0.4, p95_detection_delay_s: 60, inference_ms_per_window: 0.8, median_detection_delay_s: 45 },
    baseline: { f1: 0.75, recall: 0.62, precision: 0.95, missed_incidents: 1, false_alerts_per_hour: 0.2, p95_detection_delay_s: 90, inference_ms_per_window: 0.3, median_detection_delay_s: 75 },
    reason: "beats or complements the baseline",
    promotable: true,
  },
  mlflow_run_id: null,
  created_at: "2026-10-10T08:00:00Z",
  promoted_at: "2026-10-10T08:00:00Z",
});

export const models = { items: [model(2, "shadow"), model(1, "retired")] };

export const shadow = {
  since: minutesAgo(24 * 60),
  model: "isolation-forest:2",
  services: SERVICES.slice(0, 4).map((s, n) => ({
    service_id: id(100 + s.n),
    service: s.name,
    shadow_windows: 5760,
    shadow_alerts: [2, 18, 7, 0][n],
    rule_triggers: [1, 2, 4, 0][n],
    incidents: [0, 2, 1, 0][n],
  })),
};

export const audit = {
  items: [
    ["user", "incident.acknowledged", "incident", id(1)],
    ["agent", "investigation.completed", "investigation", id(401)],
    ["system", "incident.created", "incident", id(1)],
    ["user", "service.updated", "service", id(102)],
    ["user", "runbook.created", "runbook", id(200)],
  ].map(([actor, action, type, resource], n) => ({
    id: id(500 + n),
    actor_type: actor,
    actor_id: actor === "user" ? "commander@acme.example" : `${actor}-worker`,
    action,
    resource_type: type,
    resource_id: resource,
    ip_address: actor === "user" ? "10.0.0.12" : null,
    request_id: id(600 + n),
    metadata: {},
    created_at: minutesAgo(5 + n * 7),
  })),
  next_cursor: null,
};

export const ready = {
  status: "ready",
  checks: {
    config: { status: "ok", detail: null },
    database: { status: "ok", detail: null },
    redis: { status: "ok", detail: null },
  },
};

export const evaluations = {
  range_start: minutesAgo(30 * 24 * 60),
  range_end: NOW.toISOString(),
  detection: { incidents: 14, delay_p50_seconds: 95, delay_p95_seconds: 210 },
  investigations: { total: 22, succeeded: 17, partial: 3, failed: 2 },
  agents: { runs: 96, success_rate: 0.94, tool_calls: 412, tool_error_rate: 0.03, input_tokens: 1_840_000, output_tokens: 212_000, cost_usd: 3.87 },
  remediation: { decisions: 11, approval_rate: 0.82 },
  response: { mtta_seconds: 252, mttr_seconds: 3120 },
};

/** Request path → body. Anything else the pages ask for gets an empty 404. */
export const RESPONSES: Record<string, unknown> = {
  "/api/v1/services": services,
  "/api/v1/topology": topology,
  "/api/v1/incidents": incidents,
  "/api/v1/incident-metrics": metrics,
  "/api/v1/runbooks": runbooks,
  "/api/v1/ml/models": models,
  "/api/v1/ml/shadow": shadow,
  "/api/v1/audit-logs": audit,
  "/api/v1/ready": ready,
  "/api/v1/evaluations": evaluations,
};
