# OpsPilot

An AI-assisted Site Reliability Engineering platform. OpsPilot detects
incidents in a cloud application, investigates them with AI agents and
machine learning, proposes safe remediation, runs human-approved runbooks,
verifies recovery, and writes the postmortem.

> **Status:** v0.4.0 released: foundation, authentication and audit, service
> catalog and incident management, and the modern UI with a 3D service
> topology. Phase 5, demo microservices and telemetry, is next. See the
> [roadmap](#roadmap).

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
| Planned | LangGraph agents, scikit-learn/MLflow, OpenTelemetry + Prometheus/Grafana/Loki/Tempo, Redpanda, Terraform on AWS, Helm, Argo CD |

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
| 5 | Demo microservices and telemetry | 🚧 next |
| 6 | Detection engine | planned |
| 7 | Runbook retrieval (RAG) | planned |
| 8 | Multi-agent investigation | planned |
| 9 | Approval and safe remediation | planned |
| 10 | ML anomaly detection | planned |
| 11 | Event-driven processing | planned |
| 12 | Cloud infrastructure (AWS, Terraform) | planned |
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

## Testing

| Command | What it does |
|---|---|
| `make lint` / `make format` | ruff and eslint |
| `make typecheck` | mypy (strict) and tsc |
| `make test` | API and web unit tests (pytest, Vitest) |
| `make test-integration` | API tests against real PostgreSQL and Redis (Testcontainers) |
| `make test-e2e` | Playwright against the full stack, headless |
| `make test-lighthouse` | Lighthouse budgets (performance ≥ 85, accessibility ≥ 90) on primary pages; summary in `test-results/lighthouse/` |
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
infrastructure/     Keycloak realm (Terraform, Helm, and Argo CD come later)
tests/e2e           Playwright specs
docs/               Architecture, ADRs, SLOs, threat model
scripts/            Development helpers
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md).

## License

[MIT](LICENSE)
