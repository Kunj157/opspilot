# OpsPilot — Production-Grade Agentic CloudOps Platform

**Objective:** Build a production-grade full-stack platform that detects cloud
application incidents, investigates them using AI agents and ML, proposes safe
remediation, executes approved runbooks, validates recovery, and produces
postmortems.

---

## 1. Project Summary

OpsPilot is an AI-assisted Site Reliability Engineering platform. It will:

1. Monitor a Kubernetes-based demo application.
2. Collect metrics, logs, traces, deployment events, and Kubernetes events.
3. Detect abnormal application behavior using rules and ML.
4. Automatically create incidents.
5. Use specialized AI agents to investigate incidents.
6. Retrieve relevant runbooks and previous incidents.
7. Recommend remediation actions with supporting evidence.
8. Require human approval before executing sensitive actions.
9. Execute allow-listed Kubernetes remediation workflows.
10. Confirm whether the remediation worked.
11. Generate an incident postmortem.
12. Track operational and AI-system performance.

The project should demonstrate:

- Full-stack development
- Modern UI/UX with subtle 3D design
- Backend and API engineering
- AI agents and retrieval-augmented generation
- Traditional machine learning
- Event-driven architecture
- Cloud infrastructure
- Kubernetes
- CI/CD and GitOps
- Observability
- Security
- Testing and evaluation
- Production-readiness

---

## 2. Final Demonstration Scenario

The final demonstration must reproduce this workflow:

1. A demo application is running in Kubernetes.
2. A faulty version of the checkout service is deployed.
3. Checkout errors and latency begin increasing.
4. OpenTelemetry sends metrics, logs, and traces to the observability stack.
5. The anomaly detector identifies an abnormal error rate.
6. OpsPilot creates a new incident.
7. The incident appears on the dashboard in real time.
8. The triage agent identifies the affected service.
9. The observability agent examines metrics, logs, and traces.
10. The deployment agent identifies the latest deployment.
11. The runbook agent finds the appropriate rollback procedure.
12. The remediation agent proposes a rollback.
13. A user with the incident-commander role approves the rollback.
14. OpsPilot executes the allow-listed rollback.
15. The verification worker confirms the error rate has returned to normal.
16. The incident is marked as resolved.
17. The postmortem agent generates:
    - Incident summary
    - Impact
    - Timeline
    - Evidence
    - Root-cause hypothesis
    - Resolution
    - Follow-up actions
18. Audit logs show every user, agent, and system action.
19. Evaluation dashboards show:
    - Detection delay
    - Agent success
    - Tool-call correctness
    - Token usage
    - Model cost
    - Mean time to acknowledge
    - Mean time to resolve

---

## 3. Scope Boundaries

### 3.1 Features included

- User authentication
- Role-based access control
- Service catalog
- Incident management
- Real-time incident updates
- Metrics, logs, and trace integration
- Rule-based anomaly detection
- ML anomaly detection
- Multi-agent investigation workflow
- Runbook retrieval
- Similar-incident retrieval
- Human approval
- Allow-listed remediation
- Verification and rollback safety
- Postmortem generation
- Audit logs
- AI evaluation
- Infrastructure as code
- Kubernetes deployment
- CI/CD
- GitOps
- Security scanning
- Load testing
- Chaos/failure testing

### 3.2 Features explicitly excluded from the first release

Do not build these until the core flow is complete:

- Support for multiple cloud providers
- Autonomous destructive remediation
- Arbitrary shell execution
- Custom Kubernetes operator
- Mobile application
- Billing system
- Marketplace
- Fine-tuned foundational LLM
- Support for hundreds of integrations
- A separate microservice for every domain object

---

## 4. Technology Decisions

### 4.1 Frontend

- Next.js with TypeScript
- React
- Tailwind CSS
- shadcn/ui
- Framer Motion
- React Three Fiber for limited 3D visualization
- Drei helpers for React Three Fiber
- TanStack Query
- Zustand for limited client-side state
- Server-Sent Events for live incident updates
- React Hook Form
- Zod
- ECharts or Recharts
- Playwright
- Vitest
- Storybook

### 4.2 Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- pgvector
- Redis
- Celery initially, or Dramatiq if preferred
- Redpanda/Kafka after the main workflow works
- Server-Sent Events for live updates
- OpenAPI

### 4.3 AI and ML

- LangGraph for deterministic agent orchestration
- Provider-neutral LLM gateway
- OpenAI, Anthropic, or Amazon Bedrock as the hosted model
- Ollama as an optional local development provider
- LiteLLM as an optional provider abstraction
- pgvector for runbook and incident retrieval
- Sentence-transformer embeddings or provider embeddings
- scikit-learn
- MLflow
- Pandas
- NumPy
- XGBoost where classification is required

### 4.4 Observability

- OpenTelemetry
- OpenTelemetry Collector
- Prometheus
- Grafana
- Loki
- Tempo
- Alertmanager
- Structured JSON logs

### 4.5 Infrastructure

**Local**

- Docker Compose
- kind for local Kubernetes
- Helm
- Tilt or Skaffold for the local development loop

**Cloud**

- AWS
- Amazon EKS
- Amazon ECR
- Amazon RDS for PostgreSQL
- Amazon ElastiCache for Redis
- Amazon S3
- AWS Secrets Manager
- Route 53
- AWS Certificate Manager
- CloudFront where appropriate
- IAM roles for service accounts

**DevOps**

- Terraform
- GitHub Actions
- Argo CD
- Helm
- Argo Rollouts
- Trivy
- Semgrep
- Gitleaks
- Dependabot or Renovate
- k6
- Testcontainers
- Chaos Mesh

---

## 5. High-Level Architecture

```mermaid
flowchart LR
    U[User] --> WEB[Next.js Web Application]
    WEB --> API[FastAPI Backend]
    WEB <-->|SSE| API

    DEMO[Demo Microservices] --> OTEL[OpenTelemetry Collector]
    K8S[Kubernetes Events] --> INGEST[Event Ingestion Worker]
    OTEL --> PROM[Prometheus]
    OTEL --> LOKI[Loki]
    OTEL --> TEMPO[Tempo]

    PROM --> DETECT[Detection Worker]
    LOKI --> AGENTS[Agent Worker]
    TEMPO --> AGENTS
    DETECT --> DB[(PostgreSQL + pgvector)]
    DETECT --> BUS[Redpanda Event Bus]

    API --> DB
    API --> REDIS[(Redis)]
    BUS --> AGENTS
    AGENTS --> LLM[LLM Provider]
    AGENTS --> DB

    AGENTS --> APPROVAL[Approval Request]
    APPROVAL --> WEB
    WEB --> API
    API --> REMEDIATE[Remediation Worker]
    REMEDIATE --> K8S
    REMEDIATE --> VERIFY[Verification Worker]
    VERIFY --> PROM
    VERIFY --> DB

    API --> AUDIT[Audit Log]
    AGENTS --> AUDIT
    REMEDIATE --> AUDIT
```

---

## 6. Runtime Components

Use a small number of independently deployable services.

### 6.1 web

Responsibilities:

- Authentication UI
- Service overview
- Incident dashboard
- Incident details
- Live incident timeline
- Agent evidence display
- Remediation approval
- Postmortem display
- Evaluation dashboards
- Audit-log viewer

### 6.2 api

Responsibilities:

- Authentication and authorization
- CRUD APIs
- Incident state management
- Service catalog
- Approval APIs
- SSE connections
- Audit logging
- Input validation
- Agent job submission

### 6.3 worker

Responsibilities:

- Telemetry queries
- Incident processing
- Agent orchestration
- Runbook ingestion
- Remediation execution
- Recovery verification
- Postmortem generation
- Asynchronous notifications

Initially, use one worker project with separate queues. Split it only if
scaling requires it.

### 6.4 ml-service

Responsibilities:

- Feature processing
- Anomaly scoring
- Model loading
- Model-version reporting
- Prediction explanations
- Model health metrics

### 6.5 demo-system

Services:

- Storefront
- Checkout
- Payment
- Inventory
- Notification

Failure scenarios:

- HTTP 500 regression
- Increased latency
- Database connection exhaustion
- Memory leak
- Dependency timeout
- Invalid configuration
- Traffic spike

---

## 7. Repository Structure

```
opspilot/
├── .github/
│   ├── workflows/
│   │   ├── pull-request.yml
│   │   ├── security.yml
│   │   ├── release.yml
│   │   └── infrastructure.yml
│   └── CODEOWNERS
├── apps/
│   ├── web/
│   ├── api/
│   ├── worker/
│   └── ml-service/
├── packages/
│   ├── api-client/
│   ├── design-system/
│   ├── shared-config/
│   └── shared-schemas/
├── demo/
│   ├── services/
│   │   ├── storefront/
│   │   ├── checkout/
│   │   ├── payment/
│   │   ├── inventory/
│   │   └── notification/
│   ├── failure-injection/
│   └── load-tests/
├── ml/
│   ├── datasets/
│   ├── notebooks/
│   ├── pipelines/
│   ├── training/
│   └── evaluation/
├── infrastructure/
│   ├── terraform/
│   │   ├── modules/
│   │   └── environments/
│   │       ├── development/
│   │       ├── staging/
│   │       └── production/
│   ├── helm/
│   ├── argocd/
│   └── policies/
├── observability/
│   ├── otel-collector/
│   ├── grafana/
│   ├── prometheus/
│   ├── loki/
│   └── tempo/
├── tests/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   ├── performance/
│   ├── security/
│   ├── chaos/
│   └── agent-evals/
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── api/
│   ├── runbooks/
│   ├── threat-model/
│   ├── screenshots/
│   └── demo/
├── scripts/
├── docker-compose.yml
├── Makefile
├── DEVELOPMENT_PLAN.md
├── CONTRIBUTING.md
└── README.md
```

---

## 8. Git Workflow

> The authoritative branch model, commit rules, and self-review process live in
> [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md). This section is a
> summary.

### 8.1 Branches

- `main`: always releasable
- `dev`: integration branch
- `feature/<name>`: new functionality
- `bugfix/<name>`: bug fixes
- `infra/<name>`: infrastructure changes
- `docs/<name>`: documentation

### 8.2 Pull-request requirements

Every pull request must include:

- Summary
- Reason for change
- Screenshots for UI changes
- Tests added or updated
- Security implications
- Migration notes
- Rollback procedure
- Definition-of-done checklist

### 8.3 Commit format

Use Conventional Commits:

```
feat(api): add incident creation endpoint
fix(worker): prevent duplicate remediation execution
test(agent): add log-analysis tool selection case
docs(architecture): document incident state machine
```

---

## 9. Development Loop to Use for Every Feature

Follow this process for every feature without skipping steps.

### Step 1: Define

Write:

- User story
- Functional requirements
- Non-functional requirements
- Acceptance criteria
- Failure cases
- Security risks
- Observability requirements

### Step 2: Design

Before coding:

- Add or update an architecture diagram.
- Define API contracts.
- Define database changes.
- Define event schemas.
- Identify authorization requirements.
- Decide how the feature will be tested.
- Decide how it can be rolled back.

### Step 3: Write tests first where practical

Add:

- Unit tests
- Integration tests
- Authorization tests
- Failure-path tests
- UI tests when applicable
- Agent evaluation cases when applicable

The tests may initially fail.

### Step 4: Implement the smallest working version

Implement only what is necessary to meet acceptance criteria. Do not
prematurely:

- Create extra services
- Add unnecessary abstractions
- Introduce new infrastructure
- Add autonomous agent behavior

### Step 5: Validate locally

```
make lint
make typecheck
make test
make test-integration
make build
```

### Step 6: Perform manual validation

Confirm:

- Happy path
- Invalid input
- Unauthorized access
- Dependency unavailable
- Timeout behavior
- Retry behavior
- Audit-log creation
- Logs and metrics emitted

### Step 7: Open a pull request

The PR pipeline must run:

1. Formatting
2. Linting
3. Type checking
4. Unit tests
5. Integration tests
6. Security scanning
7. Dependency scanning
8. Container build
9. Container scan

### Step 8: Deploy to development

Argo CD deploys the development environment. Run:

- Smoke tests
- API tests
- UI tests
- Basic performance tests

### Step 9: Validate against acceptance criteria

Record:

- Test evidence
- Screenshots
- Metrics
- Known limitations

### Step 10: Improve

If a test fails:

1. Reproduce the failure.
2. Add a regression test.
3. Fix the smallest root cause.
4. Run the complete affected test suite.
5. Redeploy.
6. Repeat validation.

---

## 10. Environment Setup

### 10.1 Required software

Install:

- Git
- Docker Desktop or Docker Engine
- Node.js LTS
- pnpm
- Python 3.12 or a supported current version
- uv
- kubectl
- kind
- Helm
- Terraform
- AWS CLI
- Argo CD CLI
- jq
- make
- k6
- trivy

### 10.2 Confirm installation

```
git --version
docker --version
node --version
pnpm --version
python --version
uv --version
kubectl version --client
kind version
helm version
terraform version
aws --version
k6 version
trivy --version
```

### 10.3 Create the repository

```
mkdir opspilot
cd opspilot
git init
mkdir -p apps packages demo ml infrastructure observability tests docs scripts
```

### 10.4 Add root automation

Create a `Makefile` with these targets:

```
install
dev
stop
lint
format
typecheck
test
test-unit
test-integration
test-e2e
test-agent
test-load
build
docker-build
kind-create
kind-delete
deploy-local
seed
inject-failure
reset-demo
```

### 10.5 Local services

The first `docker-compose.yml` should run:

- PostgreSQL with pgvector
- Redis
- Prometheus
- Grafana
- Loki
- Tempo
- OpenTelemetry Collector
- Optional local LLM through Ollama

Do not add Redpanda until the basic incident workflow works.

---

## 11. Environment Configuration

Create:

```
.env.example
.env.test
.env.local
```

Required variables:

```
APP_ENV=development
DATABASE_URL=postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot
REDIS_URL=redis://localhost:6379/0

JWT_ISSUER=
JWT_AUDIENCE=
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=

LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=
EMBEDDING_MODEL=

PROMETHEUS_URL=http://localhost:9090
LOKI_URL=http://localhost:3100
TEMPO_URL=http://localhost:3200

KUBERNETES_CONTEXT=kind-opspilot
REMEDIATION_ENABLED=false
REQUIRE_REMEDIATION_APPROVAL=true

OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Rules:

- Never commit real secrets.
- CI must run Gitleaks.
- Production secrets must come from AWS Secrets Manager.
- Secret values must never be included in agent prompts or logs.

---

## 12. Database Design

### 12.1 Core tables

**organizations**

```
id
name
slug
created_at
updated_at
```

**users**

```
id
organization_id
external_auth_id
email
display_name
status
created_at
updated_at
```

**roles** — initial roles:

- viewer
- operator
- incident-commander
- administrator

**services**

```
id
organization_id
name
slug
description
owner_team
repository_url
namespace
deployment_name
health_status
created_at
updated_at
```

**incidents**

```
id
organization_id
service_id
title
description
severity
status
source
started_at
acknowledged_at
resolved_at
detection_score
assigned_user_id
version
created_at
updated_at
```

**incident_events**

```
id
incident_id
event_type
actor_type
actor_id
title
description
metadata_json
created_at
```

**evidence**

```
id
incident_id
evidence_type
source
summary
content
query
time_range_start
time_range_end
confidence
metadata_json
created_at
```

**agent_runs**

```
id
incident_id
agent_name
status
model_provider
model_name
prompt_version
input_tokens
output_tokens
estimated_cost
latency_ms
error_code
started_at
completed_at
```

**agent_tool_calls**

```
id
agent_run_id
tool_name
arguments_json
result_summary
status
duration_ms
created_at
```

**runbooks**

```
id
organization_id
title
service_id
content
version
source_url
status
embedding
created_at
updated_at
```

**remediation_proposals**

```
id
incident_id
runbook_id
action_type
description
parameters_json
risk_level
status
verification_plan_json
created_by_agent_run_id
created_at
updated_at
```

**approvals**

```
id
proposal_id
requested_by
reviewed_by
decision
comment
requested_at
reviewed_at
```

**remediation_executions**

```
id
proposal_id
idempotency_key
status
started_at
completed_at
output_json
error_message
```

**audit_logs**

```
id
organization_id
actor_type
actor_id
action
resource_type
resource_id
ip_address
request_id
metadata_json
created_at
```

**model_versions**

```
id
name
version
artifact_uri
feature_schema_json
metrics_json
status
created_at
```

---

## 13. Incident State Machine

Use an explicit state machine.

```mermaid
stateDiagram-v2
    [*] --> Detected
    Detected --> Investigating
    Investigating --> AwaitingApproval
    Investigating --> Monitoring
    AwaitingApproval --> Remediating
    AwaitingApproval --> Rejected
    Remediating --> Verifying
    Verifying --> Resolved
    Verifying --> Investigating: Verification failed
    Rejected --> Monitoring
    Monitoring --> Resolved
    Resolved --> [*]
```

Valid statuses:

```
DETECTED
INVESTIGATING
AWAITING_APPROVAL
REMEDIATING
VERIFYING
MONITORING
RESOLVED
REJECTED
```

Rules:

- State transitions must occur through one domain service.
- Every transition creates an incident event.
- Every transition creates an audit-log record.
- Invalid transitions return HTTP 409.
- Concurrent updates use optimistic locking through the `version` column.

---

## 14. API Contract

Initial API routes:

```
GET    /api/v1/health
GET    /api/v1/ready

GET    /api/v1/services
POST   /api/v1/services
GET    /api/v1/services/{service_id}
PATCH  /api/v1/services/{service_id}

GET    /api/v1/incidents
POST   /api/v1/incidents
GET    /api/v1/incidents/{incident_id}
PATCH  /api/v1/incidents/{incident_id}
POST   /api/v1/incidents/{incident_id}/acknowledge
POST   /api/v1/incidents/{incident_id}/investigate
POST   /api/v1/incidents/{incident_id}/resolve
GET    /api/v1/incidents/{incident_id}/events
GET    /api/v1/incidents/{incident_id}/stream

GET    /api/v1/incidents/{incident_id}/evidence
GET    /api/v1/incidents/{incident_id}/agent-runs

GET    /api/v1/runbooks
POST   /api/v1/runbooks
GET    /api/v1/runbooks/{runbook_id}
POST   /api/v1/runbooks/reindex

GET    /api/v1/remediations/{proposal_id}
POST   /api/v1/remediations/{proposal_id}/approve
POST   /api/v1/remediations/{proposal_id}/reject
POST   /api/v1/remediations/{proposal_id}/execute

GET    /api/v1/audit-logs
GET    /api/v1/evaluations
GET    /api/v1/model-versions
```

All mutating requests must support or generate:

```
X-Request-ID
Idempotency-Key
```

---

## 15. Event Contracts

Once the synchronous MVP works, add Redpanda.

Initial event topics:

```
telemetry.anomaly.detected.v1
incident.created.v1
incident.investigation.requested.v1
incident.evidence.collected.v1
incident.remediation.proposed.v1
incident.remediation.approved.v1
incident.remediation.completed.v1
incident.verification.completed.v1
incident.resolved.v1
```

Every event must contain:

```json
{
  "event_id": "uuid",
  "event_type": "incident.created.v1",
  "event_version": 1,
  "organization_id": "uuid",
  "correlation_id": "uuid",
  "causation_id": "uuid-or-null",
  "occurred_at": "ISO-8601",
  "producer": "api",
  "payload": {}
}
```

Requirements:

- Consumers must be idempotent.
- Failed messages must be retried with exponential backoff.
- Permanently failed messages go to a dead-letter topic.
- Event schemas must be versioned.
- Sensitive content must not be placed in event payloads.

---

## 16. UI and 3D Design Specification

### 16.1 Design direction

The UI must be **modern, three-dimensional, and minimal**, built on a
**distinctive but restrained colour palette**. It should feel like a calm,
precise command center, not a game and not a generic "dark navy + neon"
dashboard.

**Modern**

- Clean typographic hierarchy: one sans-serif for UI (e.g. Inter or Geist),
  one monospace for IDs, queries, and logs (e.g. Geist Mono / JetBrains Mono).
- Generous spacing, a strict 4 px spacing scale, and consistent radii.
- Fast, purposeful motion (150–250 ms, ease-out) for state changes only.
- Dark-first; a light theme is optional later and uses the same token names.

**Three-dimensional**

Depth is part of the visual language, not decoration:

- **Layered elevation** — every surface sits on a defined elevation level
  (background → surface-1 → surface-2 → surface-3), separated by tone,
  hairline borders, and soft layered shadows rather than heavy gradients.
- **Subtle perspective** — cards tilt slightly toward the pointer (max ~4°)
  and lift on hover; disabled under reduced motion.
- **3D service topology** (React Three Fiber) on the Command Center as the
  signature element: low-poly nodes, soft lighting, gentle depth of field.
- **3D accents elsewhere stay small**: a slowly rotating wireframe grid on
  the login page, depth-stacked incident cards in the timeline.
- Glass is used sparingly — only for overlays (drawers, command palette)
  that float above live content.

**Minimal**

- ~90% of every screen is neutral graphite tones. Colour is information.
- **One signature accent** — *Iris* — is the colour of OpsPilot itself: it
  marks primary actions, focus rings, selection, and **AI agent activity**
  (an investigation in progress pulses in Iris). Nothing else uses it.
- **Status colours are reserved for status** (healthy, degraded, critical)
  and are always paired with an icon and a text label.
- No gradients on text, no rainbow charts, no decorative glow. A soft glow is
  allowed only on a node or badge whose state is actively changing.

**Avoid**

- Generic navy + cyan/purple neon palettes
- Constant or looping animations
- Large 3D assets or textures
- Low-contrast text (every text token meets WCAG AA on every surface)
- Particle effects
- Animations that interfere with incident response

### 16.2 Design tokens — "Graphite & Iris"

All colours are defined once as CSS variables (and mirrored in the Tailwind
theme and the R3F materials). Components never use raw hex values.

```css
:root {
  /* Neutrals — cool graphite, slightly desaturated */
  --background: #0b0c0e;
  --surface-1: #121418;
  --surface-2: #181b20;
  --surface-3: #20242b;
  --surface-glass: rgba(24, 27, 32, 0.72);

  --text-primary: #edeef0;    /* 14.9:1 on surface-2 */
  --text-secondary: #a6abb5;  /*  7.5:1 on surface-2 */
  --text-muted: #868c97;      /*  4.9:1 on surface-2 */

  --border: rgba(255, 255, 255, 0.08);
  --border-strong: rgba(255, 255, 255, 0.14);

  /* Signature accent — Iris: actions, focus, selection, AI activity */
  --accent: #a79bff;          /*  7.2:1 on surface-2 */
  --accent-hover: #bbb2ff;
  --accent-subtle: rgba(167, 155, 255, 0.12);
  --on-accent: #0b0c0e;

  /* Status — only for status, always with icon + label */
  --status-healthy: #5cc98b;
  --status-degraded: #e3b34c;
  --status-critical: #ef5f5f;
  --status-unknown: #868c97;

  /* Depth */
  --shadow-1: 0 1px 2px rgba(0, 0, 0, 0.30);
  --shadow-2: 0 4px 12px rgba(0, 0, 0, 0.28), 0 1px 2px rgba(0, 0, 0, 0.30);
  --shadow-3: 0 16px 40px rgba(0, 0, 0, 0.36), 0 2px 6px rgba(0, 0, 0, 0.30);
  --radius-sm: 8px;
  --radius-card: 14px;
  --radius-lg: 20px;

  /* Motion */
  --duration-fast: 150ms;
  --duration-base: 220ms;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
}
```

Palette rules:

- Contrast is verified in CI (token contrast test) — any token change that
  drops below WCAG AA fails the build.
- Charts use neutrals plus at most one status colour or Iris to highlight;
  multi-series charts use tints of the neutral scale, not a rainbow.
- The palette is the product's identity: do not introduce a new hue without
  updating this section in the same PR.

### 16.3 Primary pages

**Login**

- Product logo
- Slowly rotating 3D wireframe grid in graphite with a faint Iris horizon
  (static under reduced motion)
- OIDC login button
- No heavy WebGL requirement

**Command Center** — contains:

- Active incident count
- Healthy/degraded/critical services
- Mean time to acknowledge
- Mean time to resolve
- Recent deployments
- Live alert stream
- 3D service topology
- Incident severity graph

**Service Topology** — use React Three Fiber. Each service is represented as a
node:

- `--status-healthy`: healthy
- `--status-degraded`: degraded
- `--status-critical`: critical
- `--accent` (Iris) pulse: being investigated by an agent
- Neutral (`--border-strong`) edge: healthy dependency, with latency label
- `--status-critical` edge: failing dependency

Node shape and an on-hover label also encode status, so colour is never the
only signal.

Interactions:

- Rotate through pointer drag
- Zoom within strict limits
- Select a service
- Open service details
- Highlight dependencies
- Show latency along dependency edges

Provide a non-3D accessible fallback.

**Incident Detail** — layout:

```
┌────────────────────────────────────────────────────┐
│ Incident title, severity, state, service, duration │
├─────────────────────┬──────────────────────────────┤
│ Timeline            │ Agent investigation          │
│                     │ - Hypothesis                 │
│ - Detected          │ - Confidence                 │
│ - Investigation     │ - Evidence                   │
│ - Proposal          │ - Tool calls                 │
│ - Approval          │ - Sources                    │
│ - Verification      │                              │
├─────────────────────┴──────────────────────────────┤
│ Metrics | Logs | Traces | Deployment changes       │
├────────────────────────────────────────────────────┤
│ Remediation proposal and approval controls         │
└────────────────────────────────────────────────────┘
```

**AI Evaluation** — display:

- Tool-call accuracy
- Retrieval relevance
- Groundedness
- Investigation success rate
- Average latency
- Token usage
- Cost per incident
- Failure categories

### 16.4 3D implementation rules

- Dynamically import the 3D topology.
- Do not server-render the WebGL canvas.
- Keep the node count below a reasonable limit.
- Use instancing if the topology grows.
- Pause animation when the browser tab is hidden.
- Reduce rendering quality on low-powered devices.
- Respect `prefers-reduced-motion`.
- Add a 2D topology fallback.
- Keep core actions outside the WebGL canvas.
- The application must remain usable if WebGL fails.

Example component boundary:

```tsx
const ServiceTopology3D = dynamic(
  () => import("@/components/topology/service-topology-3d"),
  {
    ssr: false,
    loading: () => <TopologySkeleton />
  }
);
```

### 16.5 UI acceptance criteria

- Lighthouse performance score of at least 85 on primary pages
- Accessibility score of at least 90
- No critical action available only through 3D controls
- Keyboard navigation works
- Color is not the only status indicator
- Layout works at 1440 px, 1024 px, 768 px, and 390 px
- Initial JavaScript bundle is monitored
- 3D topology loads lazily
- Reduced-motion mode disables nonessential animations
- All text and status colour tokens meet WCAG AA contrast on every surface
- Only the tokens in §16.2 are used; no raw hex values in components

---

## 17. Agent Architecture

### 17.1 Agent workflow

```mermaid
flowchart TD
    START[Incident Created] --> TRIAGE[Triage Agent]
    TRIAGE --> OBS[Observability Agent]
    OBS --> DEPLOY[Deployment Agent]
    DEPLOY --> RETRIEVE[Runbook Retrieval Agent]
    RETRIEVE --> SYNTH[Investigation Synthesis]
    SYNTH --> DECIDE{Enough evidence?}
    DECIDE -->|No| OBS
    DECIDE -->|Yes| REM[Remediation Proposal Agent]
    REM --> POLICY[Deterministic Policy Check]
    POLICY --> APPROVAL[Human Approval]
    APPROVAL --> EXECUTE[Allow-listed Tool Execution]
    EXECUTE --> VERIFY[Deterministic Verification]
    VERIFY --> POST[Postmortem Agent]
```

### 17.2 Agent responsibilities

**Triage agent**

Inputs:

- Incident metadata
- Triggering alert
- Service metadata
- Recent related incidents

Outputs:

- Suspected affected service
- Severity recommendation
- Investigation plan
- Required tools

**Observability agent**

Allowed tools:

```
query_service_metrics
search_service_logs
get_trace_summary
get_service_dependencies
```

It must return:

- Query performed
- Time range
- Evidence summary
- Source reference
- Confidence

**Deployment agent**

Allowed tools:

```
get_recent_deployments
get_kubernetes_rollout_status
get_recent_configuration_changes
get_commit_metadata
```

**Runbook agent**

Allowed tools:

```
search_runbooks
get_runbook
search_similar_incidents
```

**Remediation agent**

It creates a proposal but cannot execute it. Allowed proposal types:

```
ROLLBACK_DEPLOYMENT
RESTART_DEPLOYMENT
SCALE_DEPLOYMENT
PAUSE_ROLLOUT
NO_ACTION
```

**Postmortem agent**

Uses only collected evidence. It must distinguish:

- Confirmed facts
- Strong hypotheses
- Weak hypotheses
- Unknown information

### 17.3 Structured output

All agent responses must use validated schemas. Example:

```json
{
  "summary": "Checkout errors increased after deployment v1.4.2.",
  "hypotheses": [
    {
      "description": "The latest checkout deployment introduced the regression.",
      "confidence": 0.91,
      "supporting_evidence_ids": ["evidence-1", "evidence-4"],
      "contradicting_evidence_ids": []
    }
  ],
  "recommended_next_actions": [
    {
      "tool": "get_kubernetes_rollout_status",
      "reason": "Confirm the deployment is fully rolled out."
    }
  ]
}
```

### 17.4 Agent safety rules

- No arbitrary shell access.
- No arbitrary SQL access.
- No unrestricted Kubernetes API.
- Tool parameters are schema-validated.
- Namespace and resource allow lists are enforced.
- Retrieved documents are untrusted input.
- Runbook text cannot grant additional permissions.
- Prompt content must never override application policy.
- Sensitive data is redacted before model calls.
- All model and tool activity is audited.
- High-risk actions require human approval.
- Deterministic code executes remediation, not generated commands.

---

## 18. Machine Learning Plan

### 18.1 Initial objective

Detect abnormal HTTP error rates and latency for each service.

### 18.2 Baseline detector

Implement a rolling statistical detector first.

Features:

- Request rate
- Error rate
- P50 latency
- P95 latency
- P99 latency
- CPU utilization
- Memory utilization
- Pod restart count
- Replica availability

Baseline logic:

```
1. Create a rolling window.
2. Calculate recent mean and standard deviation.
3. Calculate a z-score for the current measurement.
4. Combine normalized feature scores.
5. Trigger when:
   - score exceeds threshold,
   - minimum traffic is present,
   - condition persists for N windows.
```

### 18.3 ML detector

After the baseline works, train an Isolation Forest.

Training data:

- Normal traffic
- Traffic spikes
- Injected 500 errors
- Latency injection
- Memory pressure
- Pod restarts
- Dependency failures

Prevent leakage:

- Split data chronologically.
- Do not randomly split adjacent time-series rows.
- Keep one or more failure runs exclusively for testing.

### 18.4 Evaluation metrics

Track:

- Precision
- Recall
- F1 score
- False alerts per hour
- Median detection delay
- P95 detection delay
- Missed incidents
- Inference latency

### 18.5 Model promotion requirements

A model can be promoted only if:

- It beats the statistical baseline on the selected primary metric.
- False alerts remain below the accepted threshold.
- Its feature schema is versioned.
- The artifact is registered in MLflow.
- Inference latency meets the SLO.
- Reproducible training code exists.
- A rollback model is available.

### 18.6 Shadow deployment

Deploy the ML detector in shadow mode:

1. Continue using the baseline for production decisions.
2. Run the ML model on the same input.
3. Store its predictions.
4. Compare model predictions with known injected failures.
5. Promote only after evaluation.

---

## 19. Detailed Implementation Phases

### Phase 0 — Planning and Documentation

**Tasks**

- Create the Git repository.
- Add `README.md`.
- Add `DEVELOPMENT_PLAN.md`.
- Add `CONTRIBUTING.md`.
- Add an MIT or Apache 2.0 license.
- Create initial architecture diagrams.
- Write ADR-001 for the technology stack.
- Write ADR-002 for modular monolith versus microservices.
- Write ADR-003 for human-approved remediation.
- Create a project board.
- Create milestones for every phase.
- Define initial SLOs.
- Define the threat-model scope.

**Validation**

- Another developer can understand the product from the README.
- The demo scenario is documented.
- The architecture identifies all trust boundaries.
- The initial scope has explicit exclusions.

**Exit criteria**

- Documentation reviewed
- Repository initialized
- Work items created
- Architecture agreed upon

### Phase 1 — Local Development Foundation

**Step 1: Bootstrap frontend**

```
pnpm create next-app apps/web --typescript --tailwind --eslint --app
cd apps/web
pnpm add @tanstack/react-query zustand zod react-hook-form
pnpm add framer-motion three @react-three/fiber @react-three/drei
pnpm add echarts
pnpm add -D vitest @testing-library/react @playwright/test
```

**Step 2: Bootstrap API**

```
mkdir -p apps/api
cd apps/api
uv init
uv add fastapi uvicorn sqlalchemy alembic psycopg pydantic-settings
uv add redis structlog httpx prometheus-client
uv add --dev pytest pytest-asyncio pytest-cov ruff mypy
```

**Step 3: Add PostgreSQL and Redis**

Create Docker Compose definitions for PostgreSQL and Redis.

**Step 4: Add API health routes**

```
GET /api/v1/health
GET /api/v1/ready
```

`health` verifies the process is alive. `ready` verifies:

- Database connection
- Redis connection
- Required configuration

**Step 5: Add structured logging**

Every log must include, where available:

```
timestamp
level
service
environment
request_id
trace_id
user_id
organization_id
message
```

**Step 6: Add frontend API connectivity**

Create a typed API client and display backend readiness.

**Tests**

- API health unit test
- Database readiness integration test
- Redis readiness integration test
- Frontend API-state test
- Docker Compose startup smoke test

**Exit criteria**

`make dev` must start the frontend, API, PostgreSQL, and Redis successfully.

### Phase 2 — Authentication, RBAC, and Audit Logs

**Tasks**

- Configure an OIDC provider.
- Add login and logout.
- Validate issuer, audience, expiration, and signature.
- Create organization and user records on first login.
- Add role mappings.
- Add backend authorization dependencies.
- Add frontend route protection.
- Create audit-log middleware.
- Redact secrets and authorization headers.
- Add an audit-log UI.

**Authorization matrix**

| Action | Viewer | Operator | Incident Commander | Admin |
|---|---|---|---|---|
| View services | Yes | Yes | Yes | Yes |
| View incidents | Yes | Yes | Yes | Yes |
| Start investigation | No | Yes | Yes | Yes |
| Approve remediation | No | No | Yes | Yes |
| Manage users | No | No | No | Yes |
| Manage runbooks | No | Yes | Yes | Yes |
| View audit logs | No | No | Yes | Yes |

**Tests**

- Missing token returns 401.
- Invalid token returns 401.
- Insufficient role returns 403.
- Cross-organization resource access returns 404 or 403.
- Approval requires the correct role.
- Mutations create audit records.
- Sensitive headers do not appear in logs.

**Exit criteria**

No protected API can be called without valid identity and authorization.

### Phase 3 — Service Catalog and Incident Management

**Tasks**

- Implement service database model.
- Implement incident database model.
- Implement incident-event model.
- Add Alembic migrations.
- Implement service APIs.
- Implement incident APIs.
- Add state-machine validation.
- Add optimistic locking.
- Add incident timeline.
- Add incident list filtering.
- Add SSE live updates.

**Incident filters**

- Status
- Severity
- Service
- Date range
- Assigned user
- Detection source

**UI tasks**

- Command-center shell
- Responsive sidebar
- Service cards
- Incident table
- Severity badges
- Incident details
- Live timeline
- Loading skeletons
- Empty states
- Error boundaries

**Tests**

- Create incident
- Reject invalid severity
- Reject invalid state transition
- Prevent stale concurrent update
- Filter incident list
- Verify organization isolation
- Verify timeline event creation
- Verify SSE update delivery
- Verify reconnect behavior

**Exit criteria**

A user can manually create, investigate, and resolve an incident through the
UI.

### Phase 4 — Modern UI and 3D Service Topology

**Step 1: Build the design system** — colors, typography, spacing, buttons,
inputs, cards, badges, dialogs, drawers, toasts, tables, tabs, timeline
components.

**Step 2: Build a 2D topology first** — render services and dependencies in a
normal React component. This ensures a fallback exists before adding 3D.

**Step 3: Build the 3D topology** using:

- React Three Fiber
- Drei
- Instanced meshes where appropriate
- Minimal lights
- Low-poly geometry
- CSS labels or HTML overlays

**Step 4: Add interaction**

- Hover state
- Selection
- Dependency highlighting
- Camera focus
- Health animation
- Click-through to service details

**Step 5: Add performance safeguards**

- Dynamic import
- Lazy loading
- Reduced-motion support
- Pause when not visible
- Cap device pixel ratio
- Use adaptive quality
- Fall back to 2D after WebGL errors

**Tests**

- Component tests for topology controls
- Browser test for service selection
- Keyboard navigation test
- Reduced-motion test
- WebGL failure fallback test
- Lighthouse test
- Visual regression snapshots

**Exit criteria**

The dashboard has a polished modern appearance, but all operational actions
remain accessible without 3D.

### Phase 5 — Demo Microservices and Telemetry

**Tasks**

- Build or adapt the five demo services.
- Instrument HTTP requests with OpenTelemetry.
- Add trace propagation.
- Emit structured logs.
- Expose Prometheus metrics.
- Add Kubernetes manifests.
- Create a kind cluster.
- Deploy the demo system.
- Deploy the OpenTelemetry Collector.
- Deploy Prometheus, Loki, Tempo, and Grafana.
- Create dashboards.

**Required metrics**

```
http_requests_total
http_request_duration_seconds
http_errors_total
service_dependency_requests_total
process_cpu_usage
process_memory_usage
kube_pod_container_status_restarts_total
kube_deployment_status_replicas_available
```

**Required trace attributes**

```
service.name
service.version
deployment.environment
http.request.method
http.response.status_code
url.path
error.type
k8s.namespace.name
k8s.pod.name
```

**Validation procedure**

1. Send a request through the storefront.
2. Confirm one distributed trace crosses the expected services.
3. Confirm logs include the same trace ID.
4. Confirm Prometheus stores request metrics.
5. Confirm Grafana displays the service.
6. Force a 500 response.
7. Confirm error logs, metrics, and traces are correlated.

**Exit criteria**

A request can be followed from the UI through metrics, logs, and traces.

### Phase 6 — Detection Engine

**Step 1: Implement telemetry query adapters**

```python
class MetricsProvider:
    async def query_range(self, query, start, end, step): ...

class LogsProvider:
    async def search(self, query, start, end, limit): ...

class TracesProvider:
    async def search(self, service, start, end, limit): ...
```

Implement Prometheus, Loki, and Tempo adapters.

**Step 2: Add a rule-based detector**

```
If:
  request volume >= minimum volume
  AND error rate >= configured threshold
  AND condition persists for three windows
Then:
  create or update an incident
```

**Step 3: Add deduplication**

Deduplication key: `organization + service + detector + failure category`.
Do not create multiple active incidents for the same condition.

**Step 4: Add anomaly scoring**

Store detector, score, threshold, features, model version, and evaluation
window.

**Step 5: Add cooldown behavior**

Prevent incident flapping through trigger persistence, recovery persistence,
cooldown period, and hysteresis.

**Tests**

- No incident below threshold
- Incident created above threshold
- Low traffic does not trigger
- Persistent breach triggers
- Single spike does not trigger
- Duplicate alert updates existing incident
- Recovery changes state appropriately
- Prometheus outage is handled
- Delayed data is handled

**Exit criteria**

The system reliably creates one incident when the demo service experiences a
sustained error increase.

### Phase 7 — Runbook RAG

**Step 1: Write initial runbooks**

```
checkout-high-error-rate.md
payment-timeout.md
deployment-rollback.md
pod-crash-loop.md
database-connection-exhaustion.md
high-memory-usage.md
```

Every runbook should include: Title, Scope, Symptoms, Prerequisites,
Investigation steps, Safe actions, High-risk actions, Verification, Rollback,
Escalation, Owner, Version.

**Step 2: Build ingestion**

1. Read document.
2. Sanitize content.
3. Extract metadata.
4. Split by semantic headings.
5. Generate embeddings.
6. Store content and vector.
7. Save source and version.

**Step 3: Build retrieval**

Filter by organization, service, environment, and runbook status. Return chunk
content, runbook ID, heading, similarity score, source reference, and version.

**Step 4: Defend against prompt injection**

- Mark retrieved content as untrusted.
- Never treat retrieved instructions as system policy.
- Remove or flag suspicious text.
- Do not expose arbitrary tools.
- Keep tool permissions outside the model.
- Include adversarial runbooks in the test suite.

**Tests**

- Correct runbook appears in top results.
- Unrelated runbook ranks lower.
- Organization filters work.
- Deleted runbooks are not retrieved.
- Updated runbooks replace old embeddings.
- Prompt-injection content cannot trigger a tool.
- Responses include citations.

**Exit criteria**

The correct runbook is retrieved for each defined demo incident with
measurable top-k accuracy.

### Phase 8 — Multi-Agent Investigation

**Step 1: Define LangGraph state**

```python
class InvestigationState(TypedDict):
    incident_id: str
    service_id: str
    investigation_round: int
    evidence_ids: list[str]
    hypotheses: list[dict]
    selected_runbook_ids: list[str]
    remediation_proposal_id: str | None
    errors: list[str]
```

**Step 2: Implement tools as normal application functions**

Build and test tools before connecting them to an LLM. Required tools:

- `query_service_metrics`
- `search_service_logs`
- `get_trace_summary`
- `get_service_dependencies`
- `get_recent_deployments`
- `get_kubernetes_rollout_status`
- `search_runbooks`
- `search_similar_incidents`

**Step 3: Add agents one at a time**

1. Triage agent
2. Observability agent
3. Deployment agent
4. Runbook agent
5. Synthesis node
6. Remediation proposal agent
7. Postmortem agent

**Step 4: Add limits**

Configure maximum investigation rounds, tool calls, tokens, duration, retry
count, and a per-incident cost budget.

**Step 5: Persist intermediate state**

Persist after every node so investigations can resume after failure.

**Step 6: Add deterministic fallback**

If the model fails:

- Preserve collected evidence.
- Display a partial investigation.
- Recommend manual review.
- Do not execute remediation.
- Allow the user to retry.

**Tests**

- Agent produces schema-valid output.
- Tool arguments are validated.
- Unauthorized namespace is rejected.
- Agent stops at maximum rounds.
- Model timeout is handled.
- Provider error is retried appropriately.
- Investigation resumes after worker restart.
- Evidence IDs exist.
- Every factual claim has evidence.
- Unknowns are stated as unknowns.

**Exit criteria**

The agent workflow investigates the broken checkout deployment and produces an
evidence-backed rollback proposal.

### Phase 9 — Approval and Safe Remediation

**Step 1: Define remediation policies**

| Action | Risk | Approval | Automatically executable |
|---|---|---|---|
| Read metrics | Low | No | Yes |
| Read logs | Low | No | Yes |
| Restart one demo deployment | Medium | Yes | After approval |
| Roll back demo deployment | Medium | Yes | After approval |
| Scale within configured bounds | Medium | Yes | After approval |
| Delete resource | High | Not supported | No |
| Run arbitrary shell | Critical | Not supported | No |

**Step 2: Validate proposals**

Before storing a proposal:

- Confirm action type is allow-listed.
- Confirm resource belongs to the organization.
- Confirm namespace is allow-listed.
- Confirm parameter bounds.
- Confirm a verification plan exists.
- Calculate risk.
- Reject generated shell commands.

**Step 3: Implement approval**

Approval must record reviewer, decision, timestamp, comment, proposal version,
and request ID. A user cannot approve a proposal that changed after review.

**Step 4: Implement idempotent execution**

Every execution has an idempotency key. If retried, return the previous
execution result and do not perform the action twice.

**Step 5: Implement Kubernetes adapters**

Only expose safe methods:

```
get_deployment
get_rollout_history
rollback_deployment
restart_deployment
scale_deployment_within_bounds
```

**Step 6: Implement verification**

For rollback verification:

1. Wait for deployment rollout.
2. Confirm pods are ready.
3. Check error rate over the verification window.
4. Check latency over the verification window.
5. Compare against pre-incident baseline.
6. Mark successful or failed.
7. Return to investigation if failed.

**Tests**

- Viewer cannot approve.
- Operator cannot approve.
- Incident commander can approve.
- Expired proposal cannot execute.
- Modified proposal requires reapproval.
- Duplicate requests execute only once.
- Disallowed namespace is rejected.
- Excessive replica count is rejected.
- Failed rollout is detected.
- Failed verification reopens investigation.
- Every action appears in the audit log.

**Exit criteria**

A user can approve a rollback that is safely executed and automatically
verified.

### Phase 10 — ML Anomaly Detection

**Tasks**

- Generate labeled failure scenarios.
- Save feature windows.
- Train the statistical baseline.
- Train Isolation Forest.
- Evaluate using chronological splits.
- Track runs with MLflow.
- Register model artifact.
- Expose inference endpoint.
- Deploy in shadow mode.
- Compare model and baseline.
- Add a model evaluation UI.
- Promote only after passing thresholds.

**Failure-data generation procedure** — for every scenario:

1. Reset the demo system.
2. Run stable traffic for 10–20 minutes.
3. Record the baseline window.
4. Inject one failure.
5. Record failure start.
6. Maintain failure for a fixed period.
7. Remove failure.
8. Record recovery time.
9. Save labels and metadata.
10. Repeat several times with varied traffic.

**Tests**

- Feature schema validation
- Missing-value handling
- Model artifact loading
- Prediction determinism within tolerance
- Inference latency
- Shadow prediction storage
- Model rollback
- Training reproducibility
- No future-data leakage

**Exit criteria**

The model has documented performance and is demonstrably better than, or
complementary to, the baseline.

### Phase 11 — Event-Driven Processing

Only begin this phase after the complete workflow works synchronously.

**Tasks**

- Add Redpanda.
- Define event schemas.
- Add producer abstraction.
- Add consumer groups.
- Add idempotency storage.
- Add retries.
- Add dead-letter topics.
- Add consumer-lag metrics.
- Add event replay tooling.
- Add trace context to events.

**Migration order**

1. Publish incident-created events while retaining direct calls.
2. Add a shadow consumer.
3. Compare consumer output with synchronous output.
4. Make the consumer authoritative.
5. Remove the direct invocation.
6. Repeat for each workflow stage.

**Tests**

- Duplicate event
- Out-of-order event
- Consumer restart
- Broker unavailable
- Poison message
- Dead-letter handling
- Replay
- Schema incompatibility

**Exit criteria**

Workers can restart, retry, and replay events without duplicating incidents or
remediation actions.

### Phase 12 — Cloud Infrastructure

**Step 1: Create Terraform modules**

```
network
eks
ecr
rds
redis
s3
iam
secrets
dns
observability
```

**Step 2: Create environments** — `development`, `staging`, `production`.
Use separate state and configuration.

**Step 3: Configure remote state**

- S3 backend
- State encryption
- State locking where supported by the selected approach
- Restricted IAM access

**Step 4: Configure EKS**

- Private worker nodes
- Managed node groups
- OIDC provider
- IAM roles for service accounts
- Cluster autoscaler or Karpenter
- Network policies
- Metrics server
- Ingress controller
- External Secrets Operator
- cert-manager

**Step 5: Configure databases** — RDS:

- Encryption enabled
- Automated backups
- Deletion protection for production
- Restricted security group
- SSL required
- Secrets stored outside Terraform output

**Step 6: Add cost controls**

- Use small development instances.
- Schedule non-production shutdown.
- Configure AWS Budgets.
- Add cost alerts.
- Destroy temporary load-test environments.
- Document estimated monthly cost.

**Validation**

```
terraform fmt -check
terraform validate
terraform plan
```

Also run tflint, Checkov or equivalent, an IAM policy review, and an
infrastructure smoke test.

**Exit criteria**

A new environment can be created reproducibly from Terraform without manual
console configuration.

### Phase 13 — Containers, Kubernetes, and GitOps

**Container requirements**

- Multi-stage builds
- Non-root user
- Minimal base image
- Pinned dependencies
- Read-only filesystem where possible
- Health checks
- No embedded secrets
- Signed images
- SBOM generation

**Kubernetes requirements** — every workload must define:

- Resource requests
- Resource limits
- Readiness probe
- Liveness probe
- Startup probe where necessary
- Security context
- Pod disruption budget where appropriate
- Horizontal pod autoscaler where appropriate
- Network policy
- Service account
- Graceful termination period

**GitOps flow**

```
Application repository
    ↓
GitHub Actions builds and tests
    ↓
Container pushed to ECR
    ↓
Deployment repository image tag updated
    ↓
Argo CD detects change
    ↓
Argo Rollouts performs canary deployment
    ↓
Smoke tests and metrics analysis
    ↓
Promotion or automatic rollback
```

**Canary stages:** 10% → 25% → 50% → 100% traffic.

Abort on:

- Increased HTTP 500 rate
- Latency SLO violation
- Failed readiness
- Failed smoke test

**Exit criteria**

A commit to `main` can reach development through an auditable GitOps
deployment.

---

## 20. CI/CD Pipelines

### 20.1 Pull-request pipeline

Run:

- Frontend formatting
- Frontend linting
- Frontend type checking
- Frontend unit tests
- Backend formatting
- Backend linting
- Backend type checking
- Backend unit tests
- Database migration test
- Integration tests
- Contract tests
- Gitleaks
- Semgrep
- Dependency audit
- Container build
- Trivy scan
- Terraform validation
- Helm lint

### 20.2 Main-branch pipeline

1. All PR checks
2. Build versioned images
3. Generate SBOM
4. Sign images
5. Push images
6. Update development manifests
7. Wait for Argo CD
8. Run smoke tests
9. Publish release metadata

### 20.3 Release pipeline

1. Create release candidate.
2. Deploy to staging.
3. Run end-to-end tests.
4. Run load test.
5. Run agent evaluations.
6. Run failure-injection suite.
7. Require manual approval.
8. Promote the same images to production.
9. Verify deployment.
10. Roll back automatically on failure.

---

## 21. Rigorous and Sustainable Testing Strategy

To ensure sustainable development, testing must prioritize domain logic,
structural boundaries, and deterministic AI evaluations over fragile UI
coverage. The strategy is divided into localized logic validation, boundary
contracts, deterministic AI scoring, and system resilience.

### 21.1 Unit & Contract Validation (The Foundation)

Target high test coverage for domain rules and security-critical logic, while
explicitly avoiding chasing coverage metrics for generated or trivial code.

- **Domain & Security Rules:** Unit test state transitions, authorization,
  input validation, and risk classification.
- **Agent Data Borders:** Validate feature transformations, tool parameter
  validation, agent output parsing, and deduplication logic.
- **Contract Enforcement:** Validate the OpenAPI schema, frontend client
  compatibility, event schemas, tool input/output schemas, and the ML feature
  schema.

### 21.2 Component Integration Testing

Isolate and test the interaction between the application and its critical
state stores.

- **Ephemeral Infrastructure:** Use Testcontainers to spin up isolated
  instances of PostgreSQL, Redis, and Redpanda during the test suite.
- **Database & Queues:** Test database migrations, repository methods,
  API-to-database communication, and worker-to-queue flows.
- **Resilience Logic:** Validate idempotency mechanisms, retry behavior, and
  asynchronous event processing.

### 21.3 End-to-End (E2E) User Journeys

Use Playwright to validate the critical path of an incident lifecycle. E2E
tests should remain focused on core operational journeys rather than
exhaustive UI permutations.

- **Authentication & Catalog:** Test user login and viewing service details.
- **Incident Lifecycle:** Validate creating an incident, starting an
  investigation, and viewing agent evidence.
- **Remediation & Closure:** Test approving remediation, observing execution,
  observing verification, viewing the postmortem, and reading audit records.

### 21.4 Deterministic AI & Agent Evaluations

Because LLM outputs are non-deterministic, agent testing must rely on
structured evaluation against a fixed benchmark dataset.

- **Dataset Construction:** Create a fixed dataset containing specific
  incident details, available evidence, expected tool sequences, expected
  runbooks, acceptable hypotheses, forbidden actions, and expected
  remediations.
- **Execution Evaluation:** Evaluate whether the agent correctly identifies
  the service, selects the right tools, generates valid tool arguments, and
  correctly retrieves runbooks.
- **Safety & Accuracy Scoring:** Measure citation correctness, groundedness,
  the safety of the remediation choice, and the strict refusal of unsupported
  actions.

### 21.5 Security & Boundary Hardening

Security testing must continuously run in the CI/CD pipeline to prevent
regression of trust boundaries.

- **Access Control:** Test for broken object-level authorization,
  cross-tenant access, and role escalation.
- **Standard Vulnerabilities:** Validate defenses against SQL injection,
  stored XSS, CSRF, and SSRF.
- **Agent-Specific Threats:** Actively test prompt injection defenses, secret
  leakage, malicious runbook inputs, unauthorized Kubernetes targets, and the
  replay of approval requests.

### 21.6 Performance Targets & Chaos Engineering

Ensure the system remains highly responsive under load and recovers
predictably from infrastructure degradation.

- **Performance Baselines:** Use k6 to simulate incident list reads, incident
  detail reads, SSE connections, incident creation bursts, agent-job
  submissions, and audit-log writes.
- **Latency SLOs:** API read P95 must remain below 300 ms under load. API
  mutations (excluding agent work) must remain below 500 ms. Ensure no
  synchronous API request waits for LLM completion, SSE reconnects reliably,
  and the general error rate remains below 1%.
- **Fault Injection:** Perform chaos tests simulating worker termination
  during an investigation, API restarts, Redis unavailability, Redpanda
  unavailability, LLM timeouts, Kubernetes API timeouts, PostgreSQL
  failovers, and duplicate remediation requests.

---

## 22. Validation Matrix

| Feature | Development validation | Automated test | Staging validation | Production signal |
|---|---|---|---|---|
| Authentication | Local login | Auth tests | OIDC smoke test | Login success rate |
| RBAC | Test each role | Authorization tests | Cross-role E2E | 401/403 rate |
| Detection | Inject failure | Detector tests | Failure suite | Detection delay |
| RAG | Query runbooks | Retrieval evaluation | Known incident set | Top-k accuracy |
| Agents | Fixed incident | Agent eval suite | Failure scenarios | Success/cost/latency |
| Approval | Manual approval | RBAC + replay tests | Full E2E | Approval audit rate |
| Remediation | Demo namespace | Idempotency tests | Rollback exercise | Success rate |
| Verification | Observe recovery | Verification tests | Failure/recovery test | False recovery rate |
| UI | Responsive review | Component/E2E tests | Lighthouse | Web vitals |
| ML | Notebook analysis | Pipeline tests | Shadow mode | Precision/recall |
| Infrastructure | Terraform plan | Policy scans | Environment creation | Drift alerts |

---

## 23. Full System Test Procedure

Run this before every release candidate.

### 23.1 Prepare

```
make kind-create
make deploy-local
make seed
```

Confirm:

- All pods are ready.
- API readiness passes.
- Web application loads.
- Prometheus receives metrics.
- Loki receives logs.
- Tempo receives traces.
- Worker queues are healthy.

### 23.2 Generate normal traffic

```
make load-normal
```

Validate:

- No incident is created.
- Baseline metrics are stable.
- False-alert count remains zero or within the defined threshold.

### 23.3 Inject checkout regression

```
make inject-failure SCENARIO=checkout-http-500
```

Record the injection timestamp.

### 23.4 Validate detection

- Error rate increases.
- Detector produces an anomaly score.
- Exactly one incident is created.
- Detection delay is recorded.
- Incident severity is correct.

### 23.5 Validate investigation

- Triage agent starts.
- Metrics tool is called.
- Logs tool is called.
- Deployment tool identifies the latest release.
- Relevant runbook is retrieved.
- Evidence contains valid source references.
- Agent does not claim unsupported facts.

### 23.6 Validate approval

- Proposal status is `PENDING`.
- Viewer cannot approve.
- Operator cannot approve.
- Incident commander can approve.
- Approval creates an audit record.
- Proposal cannot be changed after approval.

### 23.7 Validate remediation

- Only the configured deployment is targeted.
- Action executes once.
- Duplicate API calls do not execute twice.
- Rollout status is recorded.
- No arbitrary command is generated or executed.

### 23.8 Validate recovery

- Pods become ready.
- Error rate falls below threshold.
- Latency returns to normal.
- Recovery remains stable for the verification period.
- Incident becomes `RESOLVED`.

### 23.9 Validate postmortem

It includes:

- Correct timeline
- Impact
- Confirmed evidence
- Root-cause hypothesis
- Resolution
- Follow-up actions
- Links to evidence
- Clear uncertainty labels

### 23.10 Validate observability

Dashboards show:

- API request rate
- API errors
- Worker processing time
- Agent latency
- Tool-call latency
- LLM token usage
- Estimated cost
- Queue depth
- Detection delay
- Remediation success
- Verification outcome

### 23.11 Save release evidence

- Screenshots
- Test reports
- Agent evaluation results
- Load-test report
- Security-scan results
- Model evaluation report
- Terraform plan
- Release version

---

## 24. Failure, Fix, and Retest Procedure

Whenever validation fails, use this exact loop.

**Step 1: Stop promotion.** Do not deploy the failed version to the next
environment.

**Step 2: Record failure.** Create an issue containing environment, version,
reproduction steps, expected result, actual result, logs, trace ID,
screenshots, and severity.

**Step 3: Reproduce locally** using the same input, model version, prompt
version, runbook version, and application version.

**Step 4: Add a failing regression test.** Examples:

- Unit test for domain bug
- Integration test for database bug
- Agent evaluation for reasoning/tool bug
- Playwright test for UI bug
- Chaos test for resilience bug

**Step 5: Fix the root cause.** Do not suppress the symptom without
understanding it.

**Step 6: Run focused tests**

```
make test TARGET=<affected-component>
```

**Step 7: Run the full test suite**

```
make lint
make typecheck
make test
make test-integration
make test-e2e
make test-agent
```

**Step 8: Redeploy to development.** Repeat the failed validation scenario.

**Step 9: Redeploy to staging.** Repeat smoke tests, end-to-end tests, failure
injection, agent evaluation, and performance tests if relevant.

**Step 10: Document the result.** Close the issue only when:

- Regression test passes
- Original failure no longer occurs
- No new critical regression appears
- Documentation is updated

---

## 25. Security Checklist

**Application**

- OIDC validation enabled
- RBAC enforced on backend
- Tenant filters applied to all queries
- Input schemas applied
- Rate limits configured
- Secure headers configured
- CORS restricted
- Sensitive fields redacted
- Audit logs append-only at application level
- Error responses do not reveal internals

**AI**

- Retrieved text treated as untrusted
- Structured outputs validated
- Tool permissions enforced outside the model
- No arbitrary command tool
- No unrestricted database tool
- No secrets in prompts
- Model calls logged without sensitive payloads
- Tool-call limits configured
- Cost limits configured
- Human approval required

**Kubernetes**

- Non-root containers
- Read-only root filesystem where possible
- Service accounts per workload
- Minimal RBAC
- Network policies
- Resource limits
- Image scanning
- Signed-image verification
- Secrets externalized
- Remediation limited to demo namespaces

**Cloud**

- Private database
- Encryption at rest
- TLS in transit
- IAM least privilege
- Cloud audit logging
- Backup policy
- Budget alert
- No public Kubernetes API unless strongly restricted

---

## 26. Reliability and SLOs

### Initial application SLOs

| Area | SLO |
|---|---|
| API availability | 99.5% successful non-5xx responses over 30 days |
| API latency | 95% of non-agent API requests complete within 500 ms |
| Detection | 95% of supported injected failures detected within 120 seconds |
| Investigation | 90% of evaluation incidents produce a valid evidence-backed investigation |
| Remediation safety | 100% of mutating remediation requires valid approval; 0 arbitrary shell commands executed |
| Event processing | 99% of events processed within 60 seconds |

### Required alerts

- API error-rate increase
- API latency increase
- Database connection exhaustion
- Worker queue backlog
- Dead-letter message
- Agent failure rate
- LLM cost-budget breach
- Detection worker stopped
- Remediation failure
- Failed backup
- Certificate expiration

---

## 27. Backup and Disaster Recovery

### Back up

- PostgreSQL
- Runbook source documents
- ML model artifacts
- Terraform state
- Grafana dashboards
- Critical configuration

### Restore test

At least once before the final demo:

1. Create a backup.
2. Create a fresh test environment.
3. Restore the database.
4. Restore model artifacts.
5. Deploy the application.
6. Verify users, services, incidents, and runbooks.
7. Record restoration time.
8. Document recovery problems.

### Targets

Suggested portfolio targets:

- RPO: 24 hours
- RTO: 4 hours

These are demonstration targets, not claims about a real enterprise
deployment.

---

## 28. Suggested 12-Week Schedule

| Week | Main deliverable |
|---|---|
| 1 | Repository, architecture, local environment, CI foundation |
| 2 | Authentication, RBAC, database, audit logs |
| 3 | Service catalog, incidents, state machine, SSE |
| 4 | Modern dashboard and 3D service topology |
| 5 | Demo services, Kubernetes, OpenTelemetry |
| 6 | Detection engine and failure injection |
| 7 | Runbook ingestion and retrieval |
| 8 | Multi-agent investigation |
| 9 | Approval, remediation, and verification |
| 10 | ML training, evaluation, and shadow deployment |
| 11 | AWS, Terraform, EKS, GitOps, security hardening |
| 12 | Load tests, chaos tests, final validation, demo video |

If working part-time, expand this to 16–20 weeks.

---

## 29. Definition of Done

A feature is complete only if:

- Acceptance criteria are met.
- Code is reviewed.
- Unit tests pass.
- Integration tests pass.
- Security implications are addressed.
- Authorization is tested.
- Logs and metrics exist.
- Errors are handled.
- Documentation is updated.
- UI is responsive and accessible.
- Deployment succeeds in development.
- Rollback is documented.
- No high or critical security finding remains.
- Agent behavior is evaluated if applicable.
- Audit records exist for sensitive actions.

The complete project is finished only if:

- The final incident demo works end to end.
- The demo can be reproduced from documentation.
- Infrastructure can be recreated from Terraform.
- CI/CD deploys a release.
- A failed release can be rolled back.
- Backups can be restored.
- Agent evaluations are published.
- ML results are published.
- Load-test results are published.
- Threat model is published.
- Architecture is documented.
- A demo video is available.
- Resume metrics are based on actual measurements.

---

## 30. Final README Requirements

The final `README.md` must include:

1. Product overview
2. Demo GIF or video
3. Screenshots
4. Architecture diagram
5. Feature list
6. Technology stack
7. Local setup
8. Cloud deployment instructions
9. Failure-injection instructions
10. Agent safety design
11. ML methodology
12. Test strategy
13. Performance results
14. Security model
15. Known limitations
16. Roadmap
17. License

---

## 31. Portfolio Deliverables

Publish:

- Source code
- Architecture diagram
- Technical design document
- Threat model
- API documentation
- Runbooks
- CI/CD configuration
- Terraform code
- Helm charts
- Agent evaluation dataset
- ML evaluation notebook/report
- Load-test results
- Screenshots
- Five-minute demo video
- Longer architecture walkthrough
- Postmortem from a simulated incident

Do not publish:

- API keys
- Cloud account identifiers
- Private endpoint details
- Real secrets
- Sensitive logs
- Terraform state
- Private model prompts containing credentials or proprietary data

---

## 32. Final Demo Script

**Minute 0–1: Introduce the product.** Explain the problem, the architecture,
the safety model, and the supported incident.

**Minute 1–2: Show normal operation.** Show the 3D topology, healthy
services, metrics, normal traffic, and no active incidents.

**Minute 2–3: Inject failure.** Deploy the faulty checkout release. Show the
error rate increase, the service turning red, incident creation, and the live
incident timeline.

**Minute 3–5: Show investigation.** Show agent status, metrics evidence,
logs, trace summary, recent deployment, retrieved runbook, and root-cause
hypothesis.

**Minute 5–6: Show approval.** Show the proposed rollback, risk level,
verification plan, permission enforcement, and human approval.

**Minute 6–7: Show remediation.** Show rollback execution, Kubernetes
rollout, recovery validation, and incident resolution.

**Minute 7–8: Show engineering depth.** Show audit logs, agent evaluations,
ML metrics, GitHub Actions, Argo CD, Terraform, and Grafana dashboards.

---

## 33. Resume Bullet Templates

Replace placeholders only with measurements produced by the project.

- Built an agentic cloud-operations platform using Next.js, FastAPI,
  PostgreSQL, Kubernetes, OpenTelemetry, and AWS, correlating metrics, logs,
  traces, and deployment events across a distributed demo environment.
- Developed and evaluated a time-series anomaly-detection pipeline that
  achieved X% precision, Y% recall, and a median detection delay of Z seconds
  across reproducible failure scenarios.
- Implemented evidence-backed AI incident investigation using LangGraph,
  retrieval-augmented generation, structured tool calls, and human-approved
  remediation, reducing simulated mean time to resolution from X minutes to Y
  minutes.
- Provisioned AWS infrastructure using Terraform and deployed workloads
  through GitHub Actions, Argo CD, Helm, and canary rollouts with automated
  health analysis and rollback.
- Designed a secure remediation framework using OIDC, RBAC, namespace
  restrictions, schema-validated tools, idempotent execution, immutable audit
  events, and deterministic recovery verification.

---

## 34. Immediate Starting Checklist

Complete these tasks first and in order:

1. Create the repository.
2. Add this file as `DEVELOPMENT_PLAN.md`.
3. Create the folder structure.
4. Create the project board and milestones.
5. Bootstrap Next.js.
6. Bootstrap FastAPI.
7. Start PostgreSQL and Redis with Docker Compose.
8. Implement API health and readiness endpoints.
9. Display backend status in the frontend.
10. Add linting, formatting, typing, and unit tests.
11. Add the pull-request GitHub Actions workflow.
12. Add authentication.
13. Add organizations, users, and roles.
14. Add services and incidents.
15. Build the incident dashboard.
16. Build the 2D topology.
17. Add the optional 3D topology.
18. Build and instrument the demo services.
19. Add detection.
20. Add runbook retrieval.
21. Add agents.
22. Add approval and remediation.
23. Add verification.
24. Add ML.
25. Add Redpanda.
26. Deploy to AWS.
27. Run security, load, and chaos tests.
28. Record the final demo.
29. Publish measured results.
30. Add verified metrics to the resume.

---

## 35. Core Rule

The project must prioritize this complete vertical workflow:

```
Observe
→ Detect
→ Create incident
→ Investigate
→ Collect evidence
→ Retrieve runbook
→ Propose remediation
→ Enforce policy
→ Request human approval
→ Execute safely
→ Verify recovery
→ Resolve incident
→ Generate postmortem
→ Measure performance
```

Do not add unrelated features until this workflow works reliably, securely,
reproducibly, and with automated tests.
