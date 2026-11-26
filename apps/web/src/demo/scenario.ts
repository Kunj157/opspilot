/**
 * The static demo (NEXT_PUBLIC_DEMO=1) replays OpsPilot's demo incident in the
 * browser: checkout release 1.4.2 starts failing, the detector opens an
 * incident, the agents investigate, and a rollback waits for the visitor's
 * approval. Telemetry, deployments, evidence and the postmortem come from the
 * repository's recorded case (tests/agent-evals/investigations.json and
 * docs/postmortems/sample-checkout-bad-release.md); nothing is generated live.
 */

import type { Me } from "@opspilot/api-client";

const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const t0 = Date.now();
const at = (secondsFromStart: number) => new Date(t0 + secondsFromStart * 1000).toISOString();
const ago = (minutes: number) => at(-minutes * 60);

export const DEMO_INCIDENT_ID = id(1);
const CHECKOUT = id(102);
const PROPOSAL_ID = id(701);
const INVESTIGATION_ID = id(401);

const SERVICE_DEFS = [
  { n: 1, name: "Storefront", slug: "storefront", team: "web" },
  { n: 2, name: "Checkout", slug: "checkout", team: "payments" },
  { n: 3, name: "Payment", slug: "payment", team: "payments" },
  { n: 4, name: "Inventory", slug: "inventory", team: "fulfilment" },
  { n: 5, name: "Notification", slug: "notification", team: "platform" },
] as const;
const EDGES: [number, number][] = [
  [1, 2],
  [1, 4],
  [2, 3],
  [2, 4],
  [2, 5],
];

/** Seconds after the visitor opens the incident at which each investigation step lands. */
const STEP = { evidenceA: 4, evidenceB: 8, hypothesis: 11, proposal: 14 };
/** Seconds after approval. */
const AFTER = { executed: 4, verified: 12 };

let opened: number | null = null; // when the visitor first opened the demo incident
let approvedAt: number | null = null;
let rejectedAt: number | null = null;
let postmortemAt: number | null = null;

const since = (from: number | null) => (from === null ? -1 : (Date.now() - from) / 1000);

export function openIncident() {
  opened ??= Date.now();
}

type Phase = "investigating" | "awaiting" | "remediating" | "verifying" | "resolved" | "rejected";
function phase(): Phase {
  if (rejectedAt) return "rejected";
  if (approvedAt) {
    const s = since(approvedAt);
    return s >= AFTER.verified ? "resolved" : s >= AFTER.executed ? "verifying" : "remediating";
  }
  return since(opened) >= STEP.proposal ? "awaiting" : "investigating";
}

const STATUS: Record<Phase, string> = {
  investigating: "INVESTIGATING",
  awaiting: "AWAITING_APPROVAL",
  remediating: "REMEDIATING",
  verifying: "VERIFYING",
  resolved: "RESOLVED",
  rejected: "INVESTIGATING",
};

// ---- incidents -----------------------------------------------------------

const OTHER_INCIDENTS = [
  {
    n: 2,
    title: "Payment authorisation latency p95 over 2s",
    severity: "high",
    status: "MONITORING",
    service: 3,
    source: "detector",
    mins: 95,
  },
  {
    n: 3,
    title: "Inventory sync lagging behind orders",
    severity: "medium",
    status: "RESOLVED",
    service: 4,
    source: "manual",
    mins: 60 * 26,
  },
  {
    n: 4,
    title: "Notification e-mails delayed",
    severity: "low",
    status: "RESOLVED",
    service: 5,
    source: "alertmanager",
    mins: 60 * 50,
  },
] as const;

const versionCounter = { n: 3 };
function demoIncident() {
  const p = phase();
  const resolved = p === "resolved";
  return {
    id: DEMO_INCIDENT_ID,
    title: "High error rate on Checkout",
    description: "Checkout error rate above 5% for three consecutive windows after release 1.4.2.",
    severity: "high",
    status: STATUS[p],
    source: "detector",
    service_id: CHECKOUT,
    started_at: ago(3),
    acknowledged_at: ago(2),
    resolved_at: resolved && approvedAt ? new Date(approvedAt + AFTER.verified * 1000).toISOString() : null,
    detection_score: 0.94,
    assigned_user_id: DEMO_USER.id,
    version:
      versionCounter.n + ["investigating", "awaiting", "remediating", "verifying", "resolved", "rejected"].indexOf(p),
    created_at: ago(3),
    updated_at: new Date().toISOString(),
    allowed_transitions: resolved ? [] : p === "awaiting" || p === "rejected" ? ["MONITORING", "RESOLVED"] : [],
  };
}

function otherIncident(i: (typeof OTHER_INCIDENTS)[number]) {
  const resolved = i.status === "RESOLVED";
  return {
    id: id(i.n),
    title: i.title,
    description: null,
    severity: i.severity,
    status: i.status,
    source: i.source,
    service_id: id(100 + i.service),
    started_at: ago(i.mins),
    acknowledged_at: ago(i.mins - 4),
    resolved_at: resolved ? ago(i.mins - 48) : null,
    detection_score: i.source === "detector" ? 0.88 : null,
    assigned_user_id: DEMO_USER.id,
    version: 4,
    created_at: ago(i.mins),
    updated_at: ago(i.mins - 48),
    allowed_transitions: resolved ? [] : ["RESOLVED"],
  };
}

const allIncidents = () => [demoIncident(), ...OTHER_INCIDENTS.map(otherIncident)];

// ---- timeline events -----------------------------------------------------

type DemoEvent = {
  at: number;
  event_type: string;
  actor_type: string;
  actor_id: string | null;
  title: string;
  description: string | null;
  metadata: Record<string, unknown>;
};

function events(): (DemoEvent & { id: string; sequence: number; created_at: string })[] {
  const o = opened ?? Date.now();
  const s = (sec: number) => o + sec * 1000;
  const list: DemoEvent[] = [
    {
      at: t0 - 180_000,
      event_type: "incident.created",
      actor_type: "system",
      actor_id: "detector",
      title: "Incident opened by the detector",
      description: "checkout error rate above 5% for 3 consecutive windows (isolation-forest:2 + rule)",
      metadata: {},
    },
    {
      at: t0 - 175_000,
      event_type: "incident.anomaly_detected",
      actor_type: "system",
      actor_id: "detector",
      title: "Anomaly on Checkout",
      description: "error_rate 0.31 · requests_per_second 42",
      metadata: {},
    },
    {
      at: t0 - 120_000,
      event_type: "incident.acknowledged",
      actor_type: "user",
      actor_id: DEMO_USER.id,
      title: "Acknowledged by Demo Commander",
      description: null,
      metadata: {},
    },
    {
      at: t0 - 118_000,
      event_type: "incident.investigation_requested",
      actor_type: "user",
      actor_id: DEMO_USER.id,
      title: "Investigation started",
      description: "metrics, logs, traces, deployments, commit metadata, runbooks",
      metadata: {},
    },
    {
      at: s(STEP.evidenceA),
      event_type: "incident.evidence_collected",
      actor_type: "agent",
      actor_id: "metrics-agent",
      title: "Evidence collected: metrics and logs",
      description: "E1 to E3",
      metadata: {},
    },
    {
      at: s(STEP.evidenceB),
      event_type: "incident.evidence_collected",
      actor_type: "agent",
      actor_id: "change-agent",
      title: "Evidence collected: traces, deployments, commit",
      description: "E4 to E6",
      metadata: {},
    },
    {
      at: s(STEP.hypothesis),
      event_type: "incident.agent_update",
      actor_type: "agent",
      actor_id: "root-cause-agent",
      title: "Root-cause hypothesis recorded",
      description: "Release 1.4.2 of checkout introduced the regression (strong hypothesis, cites E1, E4, E5, E6)",
      metadata: {},
    },
    {
      at: s(STEP.proposal),
      event_type: "incident.investigation_finished",
      actor_type: "agent",
      actor_id: "supervisor",
      title: "Investigation finished",
      description: null,
      metadata: {},
    },
    {
      at: s(STEP.proposal) + 1,
      event_type: "incident.remediation_proposed",
      actor_type: "agent",
      actor_id: "remediation-agent",
      title: "Rollback proposed: checkout to revision 18",
      description: "Waiting for an incident commander",
      metadata: {},
    },
  ];
  if (approvedAt) {
    const a = (sec: number) => (approvedAt as number) + sec * 1000;
    list.push(
      {
        at: a(0),
        event_type: "incident.remediation_approved",
        actor_type: "user",
        actor_id: DEMO_USER.id,
        title: "Rollback approved by Demo Commander",
        description: null,
        metadata: {},
      },
      {
        at: a(AFTER.executed),
        event_type: "incident.remediation_executed",
        actor_type: "system",
        actor_id: "worker",
        title: "ROLLBACK_DEPLOYMENT executed on checkout",
        description: "revision 19 → 18 (1.0.0), namespace demo",
        metadata: {},
      },
      {
        at: a(AFTER.verified),
        event_type: "incident.verification_passed",
        actor_type: "system",
        actor_id: "verification-worker",
        title: "Recovery verified, incident resolved",
        description: "error rate below 2% for 3 windows vs. the pre-incident baseline",
        metadata: {},
      },
    );
  }
  if (rejectedAt) {
    list.push({
      at: rejectedAt,
      event_type: "incident.remediation_rejected",
      actor_type: "user",
      actor_id: DEMO_USER.id,
      title: "Rollback rejected by Demo Commander",
      description: "No action was taken",
      metadata: { reason: "rejected in the demo" },
    });
  }
  return list
    .filter((e) => e.at <= Date.now())
    .sort((a, b) => a.at - b.at)
    .map((e, i) => ({ ...e, id: id(800 + i), sequence: i + 1, created_at: new Date(e.at).toISOString() }));
}

// ---- investigation -------------------------------------------------------

const EVIDENCE = [
  [
    "metrics",
    "Prometheus",
    "checkout error rate 0.31 now, 0.0 before the incident",
    'sum(rate(http_requests_total{service="checkout",code=~"5.."}[1m])) / sum(rate(http_requests_total{service="checkout"}[1m]))',
    0.95,
  ],
  [
    "metrics",
    "Prometheus",
    "storefront error rate 0.18 now, 0.0 before (checkout calls fail with 502)",
    'sum(rate(http_requests_total{service="storefront",code=~"5.."}[1m])) / sum(rate(http_requests_total{service="storefront"}[1m]))',
    0.9,
  ],
  [
    "logs",
    "Loki",
    '14 error logs on checkout: "order failed (/orders, status 500)"',
    '{namespace="demo", app="checkout"} |= "error"',
    0.9,
  ],
  [
    "traces",
    "Tempo",
    "Failing span on POST /orders inside checkout, not in a dependency",
    '{ resource.service.name = "checkout" && status = error }',
    0.85,
  ],
  [
    "deployment",
    "Kubernetes",
    "Revision 19 (1.4.2) created 5 minutes before detection; revision 18 (1.0.0) was live for 24 hours",
    "rollout history deployment/checkout -n demo",
    0.95,
  ],
  [
    "change",
    "Deployment metadata",
    'Commit cf7db1a "checkout 1.4.2: retry orders on provider errors", pull request 142',
    null,
    0.8,
  ],
] as const;

function evidence() {
  const s = since(opened);
  const count = s >= STEP.evidenceB ? 6 : s >= STEP.evidenceA ? 3 : 0;
  return EVIDENCE.slice(0, count).map(([evidence_type, source, summary, query, confidence], i) => ({
    id: id(900 + i),
    evidence_type,
    source,
    summary,
    content: {},
    query,
    confidence,
    time_range_start: ago(15),
    time_range_end: ago(0),
    created_at: at(0),
  }));
}

const RESULT = {
  summary:
    "Errors on checkout began with release 1.4.2 (revision 19). The failing span is inside checkout itself, and the only change in the window is that release, so rolling back to revision 18 is the lowest-risk fix.",
  hypotheses: [
    {
      description:
        "Release 1.4.2 of checkout (pull request 142, retry orders on provider errors) introduced the regression.",
      confidence: 0.86,
      supporting_evidence: ["E1", "E4", "E5", "E6"],
    },
    {
      description: "The new retry logic amplifies load on the payment dependency.",
      confidence: 0.32,
      supporting_evidence: ["E6"],
    },
  ],
  unknowns: ["Why the change passed review and pre-release checks"],
  manual_review: false,
  runbooks: [
    { title: "Checkout high error rate", version: 3, runbook_id: id(200), score: 0.91 },
    { title: "Deployment rollback", version: 5, runbook_id: id(202), score: 0.84 },
  ],
};

function investigation() {
  const s = since(opened);
  const done = s >= STEP.proposal;
  return {
    id: INVESTIGATION_ID,
    incident_id: DEMO_INCIDENT_ID,
    status: done ? "completed" : "running",
    current_node: done
      ? null
      : s >= STEP.hypothesis
        ? "root_cause"
        : s >= STEP.evidenceA
          ? "change_analysis"
          : "collect_telemetry",
    round: 1,
    result: done ? RESULT : null,
    error: null,
    tool_calls: done ? 9 : Math.max(2, Math.floor(s / 2)),
    input_tokens: done ? 18_420 : 6_000,
    output_tokens: done ? 1_310 : 400,
    cost_usd: 0,
    created_at: ago(2),
    started_at: ago(2),
    completed_at: done ? at(STEP.proposal) : null,
  };
}

const tool = (n: number, tool_name: string, args: Record<string, unknown>, duration_ms: number) => ({
  id: id(1000 + n),
  tool_name,
  arguments: args,
  status: "succeeded",
  duration_ms,
  error: null,
});

function agentRuns() {
  const s = since(opened);
  const run = (n: number, agent_name: string, calls: ReturnType<typeof tool>[], from: number, to: number) => ({
    id: id(1100 + n),
    agent_name,
    status: s >= to ? "succeeded" : "running",
    model_provider: "ollama",
    model_name: "qwen2.5:7b",
    prompt_version: "v3",
    input_tokens: 3_000 + n * 500,
    output_tokens: 220 + n * 40,
    estimated_cost: 0,
    latency_ms: (to - from) * 1000,
    error_code: null,
    output: null,
    started_at: at(from),
    completed_at: s >= to ? at(to) : null,
    tool_calls: s >= to ? calls : calls.slice(0, 1),
  });
  return [
    run(
      1,
      "metrics",
      [
        tool(1, "prometheus_query", { service: "checkout", metric: "error_rate" }, 180),
        tool(2, "prometheus_query", { service: "storefront", metric: "error_rate" }, 160),
      ],
      0,
      STEP.evidenceA,
    ),
    run(2, "logs", [tool(3, "loki_query", { app: "checkout", contains: "error" }, 240)], 0, STEP.evidenceA),
    run(
      3,
      "traces",
      [tool(4, "tempo_search", { service: "checkout", status: "error" }, 310)],
      STEP.evidenceA,
      STEP.evidenceB,
    ),
    run(
      4,
      "changes",
      [
        tool(5, "k8s_rollout_history", { deployment: "checkout" }, 120),
        tool(6, "git_commit_metadata", { sha: "cf7db1a" }, 90),
      ],
      STEP.evidenceA,
      STEP.evidenceB,
    ),
    run(
      5,
      "runbooks",
      [tool(7, "runbook_search", { query: "checkout high error rate" }, 60)],
      STEP.evidenceB,
      STEP.hypothesis,
    ),
    run(6, "root_cause", [tool(8, "rank_hypotheses", { evidence: 6 }, 900)], STEP.evidenceB, STEP.hypothesis),
    run(
      7,
      "remediation",
      [tool(9, "propose_action", { action: "ROLLBACK_DEPLOYMENT", deployment: "checkout" }, 70)],
      STEP.hypothesis,
      STEP.proposal,
    ),
  ].filter((r) => s >= Number(r.started_at && (Date.parse(r.started_at) - t0) / 1000));
}

function proposals() {
  if (since(opened) < STEP.proposal) return [];
  const a = approvedAt;
  const sa = since(a);
  return [
    {
      id: PROPOSAL_ID,
      action_type: "ROLLBACK_DEPLOYMENT",
      description:
        "Roll checkout back from revision 19 (1.4.2) to revision 18 (1.0.0), the last version live before the errors began.",
      parameters: { deployment: "checkout", to_revision: 18, from_version: "1.4.2", to_version: "1.0.0" },
      risk_level: "low",
      status: rejectedAt ? "REJECTED" : a ? (sa >= AFTER.executed ? "EXECUTED" : "EXECUTING") : "PENDING",
      verification_plan: {
        max_error_rate: 0.02,
        max_p95_ratio_to_baseline: 1.5,
        window_minutes: 3,
        require_paused: true,
      },
      evidence_ids: [id(900), id(903), id(904), id(905)],
      runbook_id: id(202),
      version: 1,
      expires_at: new Date(Date.now() + 25 * 60_000).toISOString(),
      created_at: at(STEP.proposal),
      decision:
        a || rejectedAt
          ? {
              decision: a ? "approved" : "rejected",
              proposal_version: 1,
              reviewed_by: DEMO_USER.id,
              reviewer_name: "Demo Commander",
              comment: null,
              reviewed_at: new Date((a ?? rejectedAt) as number).toISOString(),
            }
          : null,
      execution: a
        ? {
            id: id(1201),
            status: sa >= AFTER.executed ? "succeeded" : "running",
            attempts: 1,
            started_at: new Date(a).toISOString(),
            completed_at: sa >= AFTER.executed ? new Date(a + AFTER.executed * 1000).toISOString() : null,
            output: sa >= AFTER.executed ? { version: "1.0.0" } : {},
            error_message: null,
            verification_status: sa >= AFTER.verified ? "passed" : sa >= AFTER.executed ? "pending" : null,
            verification: sa >= AFTER.verified ? { reason: "error rate 0.4% for 3 windows, p95 1.1x baseline" } : {},
            verified_at: sa >= AFTER.verified ? new Date(a + AFTER.verified * 1000).toISOString() : null,
          }
        : null,
    },
  ];
}

const POSTMORTEM_CONTENT = {
  summary:
    "Checkout release 1.4.2 (revision 19) shipped with a fault that made about half of checkout requests fail with HTTP 500, so storefront checkouts returned 502. The detector opened one incident, the investigation tied the errors to the new revision, and an incident commander approved a rollback to revision 18. Recovery was verified before the incident was resolved.",
  impact:
    "Checkout error rate rose from 0% to 31%; storefront from 0% to 18%. Browsing kept working; only purchases failed.",
  root_cause: {
    statement: "The release 1.4.2 change in checkout introduced the regression.",
    certainty: "strong_hypothesis",
    evidence: ["E4", "E5", "E6"],
  },
  findings: [
    { statement: "Checkout error rate rose from 0 to 31%", certainty: "confirmed", evidence: ["E1"] },
    {
      statement: "Storefront checkouts failed with 502 because checkout failed",
      certainty: "confirmed",
      evidence: ["E2", "E3"],
    },
    { statement: "The errors began after revision 19 was rolled out", certainty: "confirmed", evidence: ["E1", "E5"] },
    {
      statement: "The retry logic in the PR amplified load on dependencies",
      certainty: "weak_hypothesis",
      evidence: ["E6"],
    },
    { statement: "Why the change passed review and pre-release checks", certainty: "unknown", evidence: [] },
  ],
  resolution:
    "Rollback of checkout to revision 18 through the allow-listed ROLLBACK_DEPLOYMENT action, approved by an incident commander and executed once. Recovery was verified against the pre-incident baseline.",
  follow_ups: [
    "Add a canary stage or progressive rollout for checkout",
    "Alert on error rate per revision, not only per service",
    "Add a test for the retry-on-provider-error path in pull request 142's area",
  ],
  evidence: Object.fromEntries(EVIDENCE.map(([, source, summary], i) => [`E${i + 1}`, { summary, source }])),
};

function postmortem() {
  if (phase() !== "resolved") return null;
  postmortemAt ??= Date.now();
  const ready = since(postmortemAt) >= 3;
  // Like the real agent, the timeline is taken from the incident's own events, never written by the model.
  const timeline = events().map((e) => ({
    at: e.created_at,
    event: e.title,
    actor: e.actor_type === "user" ? "Demo Commander" : (e.actor_id ?? e.actor_type),
  }));
  return {
    id: id(1301),
    status: ready ? "ready" : "pending",
    content: ready ? { ...POSTMORTEM_CONTENT, timeline } : {},
    generated_by: "postmortem-agent (recorded)",
    prompt_version: "v2",
    updated_at: new Date().toISOString(),
  };
}

// ---- everything else -----------------------------------------------------

export const DEMO_USER: Me = {
  id: id(9001),
  email: "commander@demo.opspilot",
  display_name: "Demo Commander",
  organization: { id: id(9100), slug: "demo-shop" },
  roles: ["incident-commander"],
  permissions: [
    "view_services",
    "view_incidents",
    "manage_incidents",
    "start_investigation",
    "approve_remediation",
    "manage_services",
    "manage_runbooks",
    "view_audit_logs",
    "manage_users",
    "manage_models",
  ],
};

function health(n: number) {
  const p = phase();
  if (n === 2) return p === "resolved" ? "healthy" : "critical";
  if (n === 1) return p === "resolved" ? "healthy" : "degraded";
  return "healthy";
}

function services() {
  return {
    items: SERVICE_DEFS.map((s) => ({
      id: id(100 + s.n),
      name: s.name,
      slug: s.slug,
      description: `${s.name} service in the demo shop.`,
      owner_team: s.team,
      repository_url: "https://github.com/Kunj157/opspilot",
      namespace: "demo",
      deployment_name: s.slug,
      health_status: health(s.n),
      created_at: ago(60 * 24 * 14),
      updated_at: ago(5),
    })),
  };
}

function topology() {
  const p = phase();
  return {
    nodes: SERVICE_DEFS.map((s) => ({
      id: id(100 + s.n),
      name: s.name,
      slug: s.slug,
      health_status: health(s.n),
      active_incidents: s.n === 2 && p !== "resolved" ? 1 : 0,
      investigating: s.n === 2 && p === "investigating",
    })),
    edges: EDGES.map(([a, b]) => ({ source_id: id(100 + a), target_id: id(100 + b) })),
  };
}

const metrics = () => ({
  window_days: 30,
  mtta_seconds: 4 * 60 + 12,
  mttr_seconds: 52 * 60,
  acknowledged: 21,
  resolved: 18,
  active_by_severity: phase() === "resolved" ? { high: 1 } : { high: 2 },
  daily: Array.from({ length: 30 }, (_, d) => {
    const date = new Date(t0 - (29 - d) * 86_400_000).toISOString().slice(0, 10);
    const wave = (k: number) => Math.max(0, Math.round(1.5 + Math.sin((d + k) / 2.3) * 1.6));
    return { date, critical: d % 6 === 0 ? 1 : 0, high: wave(1) % 3, medium: wave(3), low: wave(5) % 2 };
  }),
});

const RUNBOOKS = [
  ["Checkout high error rate", ["checkout"], "payments", 3],
  ["Payment provider timeouts", ["payment"], "payments", 2],
  ["Deployment rollback", ["checkout", "payment", "storefront"], "platform", 5],
  ["Database connection exhaustion", ["inventory"], "fulfilment", 1],
] as const;
const runbooks = () => ({
  items: RUNBOOKS.map(([title, svc, owner, version], n) => ({
    id: id(200 + n),
    slug: title.toLowerCase().replace(/ /g, "-"),
    title,
    services: svc,
    owner,
    version,
    status: "active",
    source_url: null,
    updated_at: ago(60 * 24 * (n + 1)),
    content: `# ${title}\n\nOwner: ${owner}. Version ${version}.\n\n1. Check the error rate and the latest rollout.\n2. If errors began with a new revision, propose ROLLBACK_DEPLOYMENT.\n3. Verify recovery against the pre-incident baseline before resolving.`,
  })),
});

const model = (version: number, status: string) => ({
  id: id(300 + version),
  name: "isolation-forest",
  version,
  status,
  feature_schema: { version: "v1", features: ["request_rate", "error_rate"] },
  metrics: {
    test: { runs: [5, 6], scenarios: ["checkout-http-500", "checkout-latency"] },
    model: {
      f1: 0.87,
      recall: 0.84,
      precision: 0.91,
      missed_incidents: 0,
      false_alerts_per_hour: 0.4,
      p95_detection_delay_s: 60,
      inference_ms_per_window: 0.8,
      median_detection_delay_s: 45,
    },
    baseline: {
      f1: 0.75,
      recall: 0.62,
      precision: 0.95,
      missed_incidents: 1,
      false_alerts_per_hour: 0.2,
      p95_detection_delay_s: 90,
      inference_ms_per_window: 0.3,
      median_detection_delay_s: 75,
    },
    reason: "beats or complements the baseline",
    promotable: true,
  },
  mlflow_run_id: null,
  created_at: ago(60 * 24 * 4),
  promoted_at: ago(60 * 24 * 4),
});

const audit = () => ({
  items: events()
    .slice()
    .reverse()
    .slice(0, 12)
    .map((e, n) => ({
      id: id(500 + n),
      actor_type: e.actor_type,
      actor_id: e.actor_id,
      action: e.event_type,
      resource_type: "incident",
      resource_id: DEMO_INCIDENT_ID,
      ip_address: null,
      request_id: id(600 + n),
      metadata: {},
      created_at: e.created_at,
    })),
  next_cursor: null,
});

const evaluations = () => ({
  range_start: ago(30 * 24 * 60),
  range_end: at(0),
  detection: { incidents: 14, delay_p50_seconds: 95, delay_p95_seconds: 210 },
  investigations: { total: 22, succeeded: 17, partial: 3, failed: 2 },
  agents: {
    runs: 96,
    success_rate: 0.94,
    tool_calls: 412,
    tool_error_rate: 0.03,
    input_tokens: 1_840_000,
    output_tokens: 212_000,
    cost_usd: 0,
  },
  remediation: { decisions: 11, approval_rate: 0.82 },
  response: { mtta_seconds: 252, mttr_seconds: 3120 },
});

const detections = () => ({
  items: [
    {
      id: id(1401),
      service_id: CHECKOUT,
      detector: "isolation-forest",
      model_version: 2,
      score: 6.2,
      threshold: 0.05,
      is_anomaly: true,
      features: { error_rate: 0.31, requests_per_second: 42 },
      window_start: ago(4),
      window_end: ago(3),
      created_at: ago(3),
    },
  ],
});

// ---- request routing -----------------------------------------------------

type Answer = { status: number; body: unknown };
const json = (body: unknown, status = 200): Answer => ({ status, body });
const notFound = (): Answer => ({ status: 404, body: { detail: "Not found" } });

export function answer(method: string, path: string, search: URLSearchParams, body: unknown): Answer {
  const m = (re: RegExp) => path.match(re);
  let r: RegExpMatchArray | null;
  if (method === "GET") {
    if (path === "/api/v1/me") return json(DEMO_USER);
    if (path === "/api/v1/ready")
      return json({
        status: "ready",
        checks: {
          config: { status: "ok", detail: null },
          database: { status: "ok", detail: null },
          redis: { status: "ok", detail: null },
        },
      });
    if (path === "/api/v1/services") return json(services());
    if (path === "/api/v1/topology") return json(topology());
    if (path === "/api/v1/incident-metrics") return json(metrics());
    if (path === "/api/v1/runbooks" || path === "/api/v1/runbooks/search") return json(runbooks());
    if (path === "/api/v1/ml/models") return json({ items: [model(2, "active"), model(1, "retired")] });
    if (path === "/api/v1/ml/shadow")
      return json({
        since: ago(24 * 60),
        model: "isolation-forest:2",
        services: SERVICE_DEFS.slice(0, 4).map((s, n) => ({
          service_id: id(100 + s.n),
          service: s.name,
          shadow_windows: 5760,
          shadow_alerts: [2, 18, 7, 0][n],
          rule_triggers: [1, 2, 4, 0][n],
          incidents: [0, 2, 1, 0][n],
        })),
      });
    if (path === "/api/v1/audit-logs") return json(audit());
    if (path === "/api/v1/evaluations") return json(evaluations());
    if (path === "/api/v1/users")
      return json({ items: [{ ...DEMO_USER, is_active: true, created_at: ago(60 * 24 * 30) }], next_cursor: null });
    if (path === "/api/v1/incidents") {
      let items = allIncidents();
      // Array filters arrive exploded (status=A&status=B), the way openapi-fetch sends them.
      for (const key of ["status", "severity", "source"] as const) {
        const wanted = search.getAll(key);
        if (wanted.length) items = items.filter((i) => wanted.includes(i[key]));
      }
      const service = search.get("service_id");
      if (service) items = items.filter((i) => i.service_id === service);
      const q = search.get("q")?.toLowerCase();
      if (q) items = items.filter((i) => i.title.toLowerCase().includes(q));
      return json({ items, next_cursor: null });
    }
    if ((r = m(/^\/api\/v1\/services\/([^/]+)$/))) return json(services().items.find((s) => s.id === r![1]));
    if ((r = m(/^\/api\/v1\/runbooks\/([^/]+)$/))) return json(runbooks().items.find((b) => b.id === r![1]));
    if ((r = m(/^\/api\/v1\/incidents\/([^/]+)(\/[a-z-]+)?$/))) {
      const [, incident, sub] = r;
      const found = allIncidents().find((i) => i.id === incident);
      if (!found) return notFound();
      const demo = incident === DEMO_INCIDENT_ID;
      if (demo) openIncident();
      switch (sub) {
        case undefined:
          return json(found);
        case "/events":
          return json({ items: demo ? events() : [] });
        case "/investigation":
          return demo ? json(investigation()) : notFound();
        case "/evidence":
          return json({ items: demo ? evidence() : [] });
        case "/agent-runs":
          return json({ items: demo ? agentRuns() : [] });
        case "/proposals":
          return json({ items: demo ? proposals() : [] });
        case "/detections":
          return json(demo ? detections() : { items: [] });
        case "/postmortem": {
          const pm = demo ? postmortem() : null;
          return pm ? json(pm) : notFound();
        }
      }
    }
    return notFound();
  }
  if ((r = m(/^\/api\/v1\/proposals\/([^/]+)\/(approve|reject)$/))) {
    if (r[2] === "approve") approvedAt ??= Date.now();
    else rejectedAt ??= Date.now();
    return json(proposals()[0]);
  }
  if ((r = m(/^\/api\/v1\/incidents\/([^/]+)\/postmortem$/))) {
    const pm = postmortem();
    return pm ? json(pm) : notFound();
  }
  if ((r = m(/^\/api\/v1\/incidents\/([^/]+)\/investigation$/))) return json(investigation(), 202);
  if ((r = m(/^\/api\/v1\/incidents\/([^/]+)(\/[a-z]+)?$/))) {
    const found = allIncidents().find((i) => i.id === r![1]);
    return found ? json(found) : notFound();
  }
  void body;
  return json({ detail: "This action is not available in the demo." }, 403);
}

/** Events that have happened since the given sequence, each with the incident's current state (the SSE frame shape). */
export function streamSince(incidentId: string | null, lastSequence: number) {
  if (incidentId && incidentId !== DEMO_INCIDENT_ID) return [];
  const incident = demoIncident();
  return events()
    .filter((e) => e.sequence > lastSequence)
    .map((e) => ({ ...e, incident }));
}
