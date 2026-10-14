# Threat Model — Scope

This document fixes **what** the threat model covers. The consolidated
model, with mitigations mapped to tests and the open risks, is
[`threat-model.md`](threat-model.md).

## Method

- STRIDE per element on the data-flow diagram in
  [`../architecture/overview.md`](../architecture/overview.md).
- OWASP Top 10 for LLM applications for the agent and RAG paths.
- Every identified threat gets: an ID, the affected trust boundary
  (TB1–TB6), a mitigation, and **a test that proves the mitigation** (plan
  §21.5). Threats without a test are listed as open risks.

## Assets

| Asset | Why it matters |
|---|---|
| Kubernetes write access (remediation service account) | Highest-impact capability in the system |
| Approval records | Gate for every mutating action |
| Audit log | Accountability and incident reconstruction |
| OIDC tokens and sessions | Identity for every action |
| LLM API key, cloud credentials | Cost and data exposure |
| Incident evidence (logs, traces) | May contain customer-like or sensitive data |
| Runbooks | Influence agent reasoning |
| ML model artifacts | Drive detection decisions |

## Actors

| Actor | Capability assumed |
|---|---|
| Anonymous internet user | Can reach public endpoints |
| Authenticated low-privilege user (viewer/operator) | Valid session, tries to escalate or reach other tenants |
| Malicious runbook author / poisoned log line | Controls text that reaches the model |
| Compromised dependency or CI step | Code execution in build pipeline |
| Compromised LLM provider response | Arbitrary model output |

## In scope

- Web app and API (TB1, TB2): authentication, RBAC, tenant isolation,
  injection, XSS, CSRF, SSRF via telemetry URLs, rate limiting.
- Agent and RAG pipeline (TB3, TB4): prompt injection, data leakage to the
  provider, tool misuse, unbounded cost, ungrounded claims.
- Remediation path (TB5): action allow-list bypass, namespace escape,
  approval replay and race, duplicate execution.
- Supply chain (TB6): dependencies, container images, CI credentials,
  GitOps manifests.
- Secrets handling across all components.

## Out of scope

- Physical and host-OS security of developer machines.
- Attacks on AWS, GitHub, or the LLM provider's own infrastructure.
- The demo microservices' business logic (they are deliberately faulty).
- Denial of service beyond basic rate limiting and resource limits.
- Features outside the project scope (multi-cloud, billing, mobile apps, and similar).

## Assumptions

- The identity provider correctly authenticates users.
- The Kubernetes API server enforces its RBAC.
- TLS terminates at the ingress; internal traffic runs inside network
  policies.
- Only the demo namespaces contain workloads OpsPilot may modify.

## Deliverables and schedule

| Phase | Threat-model work |
|---|---|
| 2 | AuthN/Z and tenant-isolation threats + tests |
| 7 | RAG prompt-injection threats + adversarial runbooks |
| 8 | Agent tool-misuse, leakage, and cost threats + eval cases |
| 9 | Remediation and approval threats + replay/idempotency tests |
| 12–13 | Cloud, IAM, and supply-chain threats + scanner gates |
| 14–16 | Consolidated [`threat-model.md`](threat-model.md) with open risks |
