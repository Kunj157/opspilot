# ADR-002: Modular monolith over microservices

- Status: Accepted
- Date: 2026-10-13

## Context

OpsPilot has many domain concepts (services, incidents, evidence, runbooks,
proposals, approvals, audit logs, model versions). One developer has to
build, test, deploy, and operate all of it. A service per domain object
would multiply deployments, network failure modes, and data-consistency
problems without adding user value — the plan lists it as explicitly
excluded (§3.2).

At the same time, some workloads genuinely differ in runtime shape:
request/response latency (API), long-running and retryable jobs (agents,
remediation), and model inference with heavy dependencies (ML).

## Decision

Run **four application deployables**, split only along runtime shape:

| Deployable | Why separate |
|---|---|
| `web` | Different language and runtime |
| `api` | Latency-sensitive request handling; never waits on an LLM |
| `worker` | Long-running, retryable jobs on separate Celery queues (`detection`, `agents`, `remediation`, `verification`) |
| `ml-service` | Heavy ML dependencies and independent model rollout |

Inside `api` and `worker`, code is organized as **modules with explicit
boundaries** (`incidents`, `services`, `runbooks`, `remediation`, `audit`,
`auth`, …). Modules talk through their public service interfaces, never by
reaching into another module's tables or internals. The incident state
machine lives in one domain service used by both `api` and `worker`.

Split a module into its own deployable only when a measured scaling or
isolation need appears, and record that in a new ADR.

## Consequences

- One database schema, one migration history, transactional consistency
  across modules.
- Workers scale independently per queue without extra services.
- Module boundaries must be enforced by review and, later, an import-linter
  rule — the monolith does not enforce them for us.
- Phase 11's event bus fits naturally: modules already communicate through
  narrow interfaces that can become events.

## Alternatives considered

- **Microservice per domain** — rejected: operational cost far exceeds
  benefit for one developer and one demo system.
- **Single process for everything** — rejected: an agent investigation or
  rollback must never block or crash the API.
