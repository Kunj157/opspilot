# Threat Model

Consolidated model for OpsPilot v0.15, following the method in
[`scope.md`](scope.md): STRIDE per trust boundary on the data-flow diagram in
the [architecture overview](../architecture/overview.md#4-trust-boundaries),
plus the OWASP Top 10 for LLM applications on the agent and retrieval paths.
Every threat has a mitigation and the test that proves it. Threats without a
test are listed under [open risks](#open-risks).

Test paths are relative to the repository root; `api/unit` and `api/int` mean
`apps/api/tests/unit` and `apps/api/tests/integration`.

## TB1 — Browser → web → API

| ID | STRIDE | Threat | Mitigation | Proof |
|---|---|---|---|---|
| T1.1 | Spoofing | Forged, expired, or wrong-audience token | Asymmetric signature, issuer, audience, and expiry checks; JWKS rotation | `api/unit/test_token_verifier.py`, `api/int/test_authentication.py` |
| T1.2 | Elevation | Viewer or operator performs a privileged action | Permission dependency on every route; matrix in `auth/permissions.py` | `api/unit/test_permissions.py`, `api/int/test_authorization.py` |
| T1.3 | Info disclosure | Cross-organization access (IDOR/BOLA) | Organization filter on every query; foreign IDs return 404 | `api/int/test_authorization.py`, `api/int/test_users_api.py`, approval tests |
| T1.4 | Tampering | SQL injection through filters and search | ORM-only queries, typed parameters | `api/int/test_security_boundaries.py` (6 payloads × every filter) |
| T1.5 | Tampering | Stored XSS through incident, timeline, postmortem, or runbook text | JSON-only API, no raw-HTML rendering, `safeHref` for links | `api/int/test_security_boundaries.py`, `apps/web/src/lib/safe-href.test.ts`, web component tests |
| T1.6 | Spoofing | CSRF on the session-cookie BFF | Origin check on every mutating proxy request, SameSite cookies | `apps/web/src/app/api/v1/[...path]/route.test.ts` |
| T1.7 | Tampering | Proxy path traversal (`%2e%2e`) to reach non-`/api/v1` routes | Path confinement in the web proxy | `apps/web/src/app/api/v1/[...path]/route.test.ts` |
| T1.8 | DoS | Request floods, credential stuffing | Redis rate limits per user and per IP, stricter for sensitive actions; 429 with `Retry-After` | `api/unit/test_rate_limit.py`, `api/int/test_rate_limits.py` |
| T1.9 | Tampering | Duplicate mutations from retries | `Idempotency-Key` on every mutation, replayed responses | `api/int/test_idempotency.py`, `api/int/test_idempotent_mutations.py` |
| T1.10 | Info disclosure | Clickjacking, MIME sniffing, leaky errors | Secure headers and CSP (web and API), restrictive CORS, generic 500 body with request ID | `api/unit/test_security_headers.py`, `apps/web/src/lib/security-headers.test.ts`, `api/unit/test_error_responses.py` |
| T1.11 | Repudiation | User denies an action | Append-only audit log enforced by the database, with redaction | `api/int/test_audit_logs.py`, `api/unit/test_redaction.py` |

## TB2 — API ↔ identity provider

| ID | STRIDE | Threat | Mitigation | Proof |
|---|---|---|---|---|
| T2.1 | Spoofing | Token from another client or realm accepted | Pinned issuer and audience | `api/unit/test_token_verifier.py` |
| T2.2 | Spoofing | Login CSRF / code interception | PKCE and state in the authorization-code flow; tokens kept server-side | `tests/e2e/authentication.spec.ts`, `api/int/test_keycloak_login.py` |

## TB3 — Worker → LLM provider (OWASP LLM02, LLM10)

| ID | STRIDE | Threat | Mitigation | Proof |
|---|---|---|---|---|
| T3.1 | Info disclosure | Secrets or PII sent in prompts | Redaction before every model call; no secrets in tool output | `api/unit/test_llm_gateway.py` (prompts redacted before they leave) |
| T3.2 | DoS | Provider timeout or 5xx storm stalls the loop | Timeouts, bounded retries with backoff, partial result with evidence kept | `api/unit/test_llm_gateway.py`, `tests/chaos/test_llm_storm.py` |
| T3.3 | DoS | Cost runaway | Per-investigation limits on rounds, tool calls, tokens, duration, and cost; cost-budget alert | `api/int/test_investigation.py`, alert rules in `docs/operations/alerts.md` |

## TB4 — Runbooks and telemetry → agents (OWASP LLM01, LLM05, LLM06, LLM09)

| ID | STRIDE | Threat | Mitigation | Proof |
|---|---|---|---|---|
| T4.1 | Tampering | Prompt injection in a runbook or log line | Retrieved text marked untrusted, injection-looking text flagged and demoted | `api/unit/test_injection_flags.py`, `tests/agent-evals/retrieval.json` (adversarial runbook) |
| T4.2 | Elevation | Injected text makes the agent call a tool or act | Fixed tool list in code, schema-validated arguments, no shell/SQL/raw Kubernetes tools; deterministic policy decides remediation | `api/unit/test_investigation_tools.py`, `api/unit/test_remediation_policy.py`, injected namespace deletion case in `tests/agent-evals/investigations.json` |
| T4.3 | Tampering | Ungrounded or hallucinated claims | Hypotheses and summary claims must cite collected evidence; uncited claims dropped or marked unverified; unknowns stated | `api/unit/test_grounding.py`, `api/int/test_postmortem.py` |
| T4.4 | Info disclosure | Secret values pulled into context | Configuration-change tool reports metadata and references only, never Secret values | `api/unit/test_kube_reader.py` |

## TB5 — Remediation worker → Kubernetes

| ID | STRIDE | Threat | Mitigation | Proof |
|---|---|---|---|---|
| T5.1 | Elevation | Out-of-scope or destructive action | Four actions only (rollback, restart, bounded scale, pause rollout), namespace allow-list, replica bounds; delete and shell unsupported | `api/unit/test_remediation_policy.py`, `api/unit/test_kube_writer.py` |
| T5.2 | Spoofing | Execution without valid approval | Approval bound to the exact proposal version by an incident commander; checks repeated just before acting | `api/int/test_remediation_approval.py` |
| T5.3 | Tampering | Replayed or duplicated execution | Idempotency key, row locks, leases; decided proposals cannot be decided again | `api/int/test_remediation_execution.py`, `tests/chaos/test_worker_kill.py` |
| T5.4 | DoS | Hung Kubernetes API during remediation | Timeouts on every Kubernetes call; fails safe with an audit record, no double execution | `tests/chaos/test_kubernetes_timeout.py` |
| T5.5 | Repudiation | Action without a trail | Approval, execution, and verification all audited | `api/int/test_remediation_approval.py`, `api/int/test_recovery_verification.py` |

## TB6 — CI/CD → registry → cluster

| ID | STRIDE | Threat | Mitigation | Proof |
|---|---|---|---|---|
| T6.1 | Tampering | Vulnerable or malicious dependency | pip-audit (api, ml, demo), pnpm audit, Semgrep, digest-pinned base images | `Security` and image jobs in `.github/workflows/pull-request.yml` |
| T6.2 | Tampering | Vulnerable image | Trivy on every PR and on `main` (HIGH/CRITICAL with fixes fail) | `Image ·` jobs in CI |
| T6.3 | Spoofing | Unsigned or foreign image deployed | cosign keyless signatures + SBOM attestations; Kyverno verifies at admission (Enforce in staging and production) | `.github/workflows/images.yml`, `infrastructure/argocd/bootstrap/kyverno` |
| T6.4 | Tampering | Deploy before images exist / unreviewed deploy | Argo CD tracks `env/*` tags moved only after images are signed; production needs manual approval | `.github/workflows/images.yml`, `.github/workflows/release.yml` |
| T6.5 | Info disclosure | Secrets committed | gitleaks on all branches in CI | `Security` job in CI |
| T6.6 | Elevation | Over-privileged cloud roles | IRSA per workload, state bucket restricted to named principals, CloudTrail | `docs/security/iam-review.md`, checkov in CI |

## Kubernetes runtime

Non-root, read-only root filesystems, dedicated service accounts, minimal RBAC
(the worker can patch Deployments only in allowed namespaces), network
policies for OpsPilot and the demo shop, resource limits, PDBs. Semgrep in CI
rejects containers running as root; kubeconform validates the charts.

## Open risks

| ID | Risk | Why open | Next step |
|---|---|---|---|
| R1 | CSP keeps `'unsafe-inline'` for scripts | Next.js Cache Components are incompatible with per-request nonces | Revisit when nonces work with partial prerendering |
| R2 | Kyverno and cosign v3 signature storage not yet verified on a real cluster | No signed images have run through admission yet | Verify on the first cluster with signed images |
| R3 | Cloud controls validated statically only | No AWS account configured; Terraform never applied | `make infra-smoke` after the first apply |
| R4 | AWS Load Balancer Controller policy is broad (upstream) | Upstream-managed policy | Track in `docs/security/iam-review.md` |
| R5 | Model promotion endpoint does not scope model versions by organization | Model versions are global by design today | Decide deliberately if models become per-tenant |
| R6 | Agent evals in CI use a scripted model | Real-model scores vary and need a GPU | Run `make test-agent LLM=ollama` before releases and record results |
