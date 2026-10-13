# ADR-001: Technology stack

- Status: Accepted
- Date: 2026-10-13

## Context

OpsPilot must demonstrate full-stack, AI, ML, and cloud-infrastructure
engineering as one coherent product, built by one developer in roughly
12–20 weeks. The stack must be mainstream (so the work is legible to
reviewers and employers), well-supported for AI/ML, and runnable locally
without a cloud account until Phase 12.

## Decision

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript, Tailwind, shadcn/ui, TanStack Query, Zustand, React Three Fiber | Mainstream React stack; server components for fast pages; R3F gives the 3D topology without a separate engine |
| Live updates | Server-Sent Events | One-directional server → client updates are all the UI needs; simpler than WebSockets through proxies and load balancers |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic | Same language as the AI/ML code; typed request/response models generate OpenAPI for the TS client |
| Data | PostgreSQL + pgvector, Redis | One relational store also serves vector search, avoiding a separate vector DB |
| Jobs | Celery on Redis (Dramatiq acceptable) | Mature retries, routing to separate queues |
| Events | Redpanda, **from Phase 11 only** | Kafka API without ZooKeeper/JVM ops; deferred until the synchronous flow works |
| Agents | LangGraph behind a provider-neutral LLM gateway | Explicit, deterministic graph with persisted state; no lock-in to one model vendor |
| ML | scikit-learn, Pandas, MLflow | Isolation Forest and statistical baselines need nothing heavier; MLflow handles registry and lineage |
| Observability | OpenTelemetry → Prometheus, Loki, Tempo, Grafana | Vendor-neutral instrumentation, open-source backends that run in kind |
| Local infra | Docker Compose, kind, Helm, Tilt | Same Helm charts locally and in the cloud |
| Cloud | AWS: EKS, RDS, ElastiCache, ECR, S3, Secrets Manager | Single provider (multi-cloud explicitly out of scope) |
| Delivery | Terraform, GitHub Actions, Argo CD, Argo Rollouts | IaC + GitOps + canary with automated rollback |
| Quality | pytest, Testcontainers, Vitest, Playwright, k6, Chaos Mesh, Trivy, Semgrep, Gitleaks | Covers unit → e2e → load → chaos → supply chain |
| Package managers | pnpm (JS), uv (Python) | Fast, lockfile-first, workspace support |

## Consequences

- Two languages (TypeScript, Python); the API contract is the seam, and the
  TS client is generated from OpenAPI to keep them in sync.
- pgvector caps retrieval scale, which is acceptable for runbook-sized
  corpora.
- Deferring Redpanda means Phases 1–10 use direct calls and Celery queues;
  Phase 11 migrates stage by stage.

## Alternatives considered

- **Node.js backend** — rejected: AI/ML ecosystem is Python-first.
- **Dedicated vector database (Qdrant, Pinecone)** — rejected: one more
  service to run and secure for no benefit at this scale.
- **WebSockets** — rejected for now: bidirectional channel not needed.
- **CrewAI / autonomous agent frameworks** — rejected: less deterministic
  control flow than an explicit LangGraph state machine.
