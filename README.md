# OpsPilot

An AI-assisted Site Reliability Engineering platform. OpsPilot detects
incidents in a cloud application, investigates them with AI agents and
machine learning, proposes safe remediation, runs human-approved runbooks,
verifies recovery, and writes the postmortem.

> **Status:** v0.11.0 released. The full incident loop works on the demo, from
> detection through agent investigation, approved rollback, verification,
> and postmortem; an ML detector runs in shadow mode; and incident events
> flow through Redpanda with idempotent consumers. Phase 12, cloud
> infrastructure, is next. See the [roadmap](#roadmap).

## What it does today

- **Sign-in and access control:** OIDC login through Keycloak (PKCE, tokens
  kept server-side), role-based permissions (viewer, operator, incident
  commander, administrator) enforced in the API, and strict organization
  isolation.
- **Audit trail:** an append-only audit log, enforced by the database, with
  secret redaction and a filterable viewer.
- **Service catalog:** services with owners, namespaces, and health, plus the
  dependencies between them.
- **Incidents:** one state machine owns every status change, with optimistic
  locking, timeline events, and an audit record for each transition.
  Filters, keyset pagination, and idempotent creation are included.
- **Live updates:** server-sent events driven by PostgreSQL `NOTIFY`. Streams
  resume with `Last-Event-ID`, so nothing is lost or duplicated.
- **Command center:** active incidents, service health, MTTA and MTTR, a
  daily severity chart, a live alert stream, and the service topology as a
  lazily loaded 3D view (React Three Fiber) with an accessible 2D map and
  list fallback. Incident list and detail pages update live, with actions
  for each state.
- **Demo shop on Kubernetes:** five instrumented services on kind with
  OpenTelemetry traces, JSON logs, and Prometheus metrics correlated by
  trace ID in Tempo, Loki, and Grafana; synthetic load and faulty-release
  scenarios that a rollback undoes.
- **Detection:** a worker evaluates every service's error rate against
  Prometheus. A sustained breach opens exactly one incident on the failing
  service (callers are noted as affected), with the detector's readings as
  evidence; recovery is recorded. Measured detection delay: 81–95 s.
- **Runbooks:** versioned Markdown runbooks, chunked by section and embedded
  locally (bge-small) into pgvector. Search ranks sections by meaning with
  a boost for the affected service, cites runbook, version, and heading, and
  flags and demotes text that looks like prompt injection. Retrieval eval: top-1 100 % on the
  demo incidents. Runbook pages show versions and sections.
- **Agent investigation:** a LangGraph workflow (triage → observability →
  deployments → runbooks → synthesis → remediation) investigates each
  detector incident with read-only tools over Prometheus, Loki, Tempo,
  Kubernetes, the catalog, and the runbook library. Every hypothesis cites
  collected evidence. A deterministic policy turns the model's suggestion
  into an allow-listed proposal (for example, roll back to the previous
  release only when the errors began with the latest one) that waits for
  approval. It runs on a local model by default (qwen2.5 7B through Ollama)
  or on Claude, with tool, token, cost, and time limits, and resumes after a
  worker restart. Measured on the demo: a faulty checkout release is
  detected in about 60 s and investigated in about 10 s, with a correct
  rollback proposal.
- **Approval and safe remediation:** an incident commander approves or
  rejects the exact proposal version they reviewed. The worker then runs it
  once (idempotency key, row locks, leases) through a Kubernetes adapter
  with only three actions: roll back, restart, and scale within bounds, in
  allow-listed namespaces. Everything is checked again just before acting.
  Recovery is then verified: the rollout completes, and the error rate and
  p95 over a 3-minute window are compared with the pre-incident baseline.
  The incident is resolved, or the investigation reopens. Measured on the
  demo: approval to rollback in 1 s, resolved 3 min 20 s later.
- **Postmortems:** resolved incidents get a drafted, blameless postmortem
  whose findings are labelled confirmed, strong or weak hypothesis, or
  unknown, each citing its evidence.
- **ML anomaly detection:** labelled failure runs recorded on the demo
  cluster, versioned feature windows (traffic, errors, latency percentiles,
  restarts, availability), a robust rolling z-score baseline and an
  Isolation Forest, a chronological evaluation tracked in MLflow, and a
  promotion rule. The model runs in shadow mode: it scores every service
  each cycle and is compared with the rule and with real incidents on the
  ML detector page, but it never opens incidents. On the held-out runs the
  baseline wins (F1 0.97, no false alerts, 23 s delay), so the Isolation
  Forest stays unpromoted. See [`ml/`](ml/README.md).
- **Event-driven processing:** the incident timeline doubles as a
  transactional outbox. A relay publishes it to versioned Redpanda topics
  (envelope v1, keyed by incident, trace context in headers). Consumers are
  idempotent by event ID, retry with backoff, and park poison or failing
  messages on dead-letter topics, which can be replayed safely. Detector
  incidents can be investigated from `incident.created.v1` events instead
  of a direct call (`make events-up`, `KAFKA_BOOTSTRAP_SERVERS`,
  `EVENT_DRIVEN_INVESTIGATIONS`).
- **Design system:** Graphite & Iris tokens with contrast checked in CI,
  shared primitives (buttons, tilting cards, tabs, drawer, toasts), and
  Lighthouse budgets on primary pages.

## The end-to-end goal

1. A faulty checkout release is deployed to a Kubernetes demo shop.
2. Telemetry shows rising errors; the detector opens an incident, which
   appears on the dashboard in real time.
3. Agents investigate metrics, logs, traces, and deployments, find the
   matching runbook, and propose a rollback with evidence.
4. An incident commander approves; OpsPilot runs the allow-listed rollback,
   verifies recovery, resolves the incident, and drafts the postmortem.
5. Every user, agent, and system action is in the audit log; dashboards show
   detection delay, agent accuracy, cost, MTTA, and MTTR.

## Architecture

| Part | Technology |
|---|---|
| Web (`apps/web`) | Next.js, React, TypeScript, Tailwind CSS, TanStack Query, React Three Fiber |
| API (`apps/api`) | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Data | PostgreSQL (pgvector), Redis |
| Identity | Keycloak (OIDC) |
| Typed client (`packages/api-client`) | Generated from the API's OpenAPI schema |
| Agents | LangGraph, Ollama (local, default) or the Anthropic API |
| ML (`ml/`) | pandas, scikit-learn, MLflow |
| Events | Redpanda (Kafka API), aiokafka |
| Planned | Terraform on AWS, Argo CD |

Design notes and decisions live in [`docs/`](docs): the
[architecture overview](docs/architecture/overview.md), [SLOs](docs/architecture/slos.md),
[ADRs](docs/adr), and the [threat model scope](docs/threat-model/scope.md).

## Roadmap

Each phase ends with a tagged release.

| Phase | Scope | Status |
|---|---|---|
| 0 | Planning and documentation | ✅ v0.2.0 |
| 1 | Local development foundation | ✅ v0.2.0 |
| 2 | Authentication, RBAC, audit logs | ✅ v0.2.0 |
| 3 | Service catalog and incident management | ✅ v0.3.0 |
| 4 | Modern UI and 3D service topology | ✅ v0.4.0 |
| 5 | Demo microservices and telemetry | ✅ v0.5.0 |
| 6 | Detection engine | ✅ v0.6.0 |
| 7 | Runbook retrieval (RAG) | ✅ v0.7.0 |
| 8 | Multi-agent investigation | ✅ v0.8.0 |
| 9 | Approval and safe remediation | ✅ v0.9.0 |
| 10 | ML anomaly detection | ✅ v0.10.0 |
| 11 | Event-driven processing | ✅ v0.11.0 |
| 12 | Cloud infrastructure (AWS, Terraform) | 🚧 next |
| 13 | Containers, Kubernetes, and GitOps | planned |

## Local development

Requirements: Docker, Node 22 with pnpm (via corepack), Python 3.12 with
[uv](https://docs.astral.sh/uv/), make.

```bash
cp .env.example .env      # change the *_PORT values if 5432/6379/8000/3000/8080 are taken
make install
make dev                  # PostgreSQL, Redis, Keycloak, API, and web; Ctrl+C stops all
```

Open the web app on `WEB_PORT` (default http://localhost:3000). The API's
readiness check is at `/api/v1/ready` on `API_PORT` (default 8000).

`make dev` also starts a local Keycloak (http://localhost:8080; admin console
login `admin` / `admin`) with the `opspilot` realm from
`infrastructure/keycloak/realm-opspilot.json`. Development users all use the
password `opspilot-dev`:

| User | Organization | Role |
|---|---|---|
| `viewer` | acme | viewer |
| `operator` | acme | operator |
| `commander` | acme | incident-commander |
| `admin` | acme | administrator |
| `outsider` | globex | administrator (for cross-organization tests) |

These credentials exist only in the local realm. `make token USER=commander`
prints an access token for API calls.

## Demo stack (Kubernetes)

The demo shop (storefront, checkout, payment, inventory, notification) runs on
a local [kind](https://kind.sigs.k8s.io/) cluster with OpenTelemetry,
Prometheus, Loki, Tempo, and Grafana. Requires `kind`, `kubectl`, and `helm`.

```bash
make deploy-local          # cluster, observability stack, demo image and chart
make seed                  # register the demo services in OpsPilot (API running)
make seed-runbooks         # load docs/runbooks into the runbook library (API running)
make load-normal           # steady synthetic traffic
make inject-failure SCENARIO=checkout-http-500   # ship a faulty release
make reset-demo            # back to the healthy release
make test-telemetry        # follow one request through traces, logs, and metrics
make test-detection        # one sustained failure → exactly one incident (needs make dev)
```

With `PROMETHEUS_URL` set, `make dev` also runs the **detection worker**. Every
15 s it evaluates each catalog service's error rate. A sustained breach opens
one incident on the failing service. Callers that fail because of it are
noted as affected on that incident instead of getting incidents of their own.
Recovery is recorded on the timeline.

The worker (`make worker`) also runs the **agent investigations**. Start the
local model once with `make llm-up` (Ollama, GPU when available). Detector
incidents are investigated automatically, and the incident page shows the
hypotheses, cited evidence, tool calls, and the proposed remediation.
`make test-agent LLM=ollama` runs the agent evals on the local model.

The cluster uses its own kubeconfig (`.kube/config`), so other clusters are
never touched. It publishes fixed localhost ports: Grafana
http://localhost:33300, Prometheus :39090, Loki :33100, Tempo :33200, and the
storefront :38080. Scenarios are described in
[`demo/failure-injection`](demo/failure-injection/README.md) and the stack in
[`observability`](observability/README.md).

## Testing

| Command | What it does |
|---|---|
| `make lint` / `make format` | ruff and eslint |
| `make typecheck` | mypy (strict) and tsc |
| `make test` | API and web unit tests (pytest, Vitest) |
| `make test-integration` | API tests against real PostgreSQL and Redis (Testcontainers) |
| `make test-e2e` | Playwright against the full stack, headless |
| `make test-lighthouse` | Lighthouse budgets (performance ≥ 85, accessibility ≥ 90) on primary pages; summary in `test-results/lighthouse/` |
| `make test-ml` | ML tests: feature schema, missing values, leakage, determinism |
| `make test-agent` | Agent and retrieval evals on fixed datasets (`tests/agent-evals`) |
| `make build` | Production builds |
| `make api-client` | Regenerate the typed client from the OpenAPI schema |
| `make keycloak-smoke` | Check every dev user gets the right token claims |
| `make secrets-scan` | gitleaks |

`make help` lists every target. CI runs the same gate on every pull request,
plus a contract check on the API client, Semgrep, and dependency audits.

## Repository layout

```
apps/api            FastAPI service, migrations, tests
apps/web            Next.js app and component tests
packages/api-client Typed API client generated from OpenAPI
demo/services       Instrumented demo shop (one image, five services) and load generator
demo/failure-injection  Faulty-release scenarios
infrastructure/     Keycloak realm, kind cluster, demo-shop Helm chart
observability/      Collector, Prometheus, Loki, Tempo, Grafana manifests and dashboards
tests/e2e           Playwright specs
docs/               Architecture, ADRs, SLOs, threat model
scripts/            Development helpers
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md).

## License

[MIT](LICENSE)
