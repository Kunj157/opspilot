# ADR-003: Human-approved, allow-listed remediation

- Status: Accepted
- Date: 2026-10-13

## Context

OpsPilot's agents read untrusted input (logs, traces, runbook text) and are
driven by a non-deterministic model. Letting that output act directly on a
Kubernetes cluster would make a prompt injection or a hallucination a
production outage. The plan excludes autonomous destructive remediation and
arbitrary shell execution (§3.2) and sets a 100% approval SLO for mutating
actions (§26).

## Decision

1. **Agents propose, never execute.** The remediation agent emits a
   structured proposal with one of a fixed set of action types:
   `ROLLBACK_DEPLOYMENT`, `RESTART_DEPLOYMENT`, `SCALE_DEPLOYMENT`,
   `PAUSE_ROLLOUT`, `NO_ACTION`.
2. **Deterministic policy check before storage.** Code — not the model —
   verifies the action is allow-listed, the target belongs to the
   organization and an allow-listed namespace, parameters are within
   bounds, and a verification plan exists. Free-form commands are rejected.
3. **Human approval bound to a proposal version.** Only `incident-commander`
   or `administrator` can approve. Approval records reviewer, decision,
   comment, timestamp, proposal version, and request ID. Any change to the
   proposal invalidates the approval.
4. **Deterministic, idempotent execution.** A Kubernetes adapter exposes
   only `get_deployment`, `get_rollout_history`, `rollback_deployment`,
   `restart_deployment`, and `scale_deployment_within_bounds`. Each
   execution has an idempotency key; retries return the original result.
5. **Mandatory verification.** After execution, deterministic checks compare
   readiness, error rate, and latency with the pre-incident baseline. Failure
   returns the incident to `INVESTIGATING`.
6. **Global kill switch.** `REMEDIATION_ENABLED=false` by default;
   `REQUIRE_REMEDIATION_APPROVAL=true` cannot be disabled in staging or
   production.
7. **Everything is audited** — proposal, policy decision, approval,
   execution, verification.

## Consequences

- Mean time to resolve includes human reaction time; the demo measures and
  reports it rather than hiding it.
- The set of fixable incidents is limited to what the allow-listed actions
  cover. New action types require code, tests, and a policy-table update.
- The remediation service account needs only the RBAC verbs those adapter
  methods use, in demo namespaces only.

## Alternatives considered

- **Fully autonomous remediation** — rejected: unacceptable blast radius
  from untrusted input.
- **Model-generated `kubectl` commands with approval** — rejected: a human
  cannot reliably review arbitrary commands under incident pressure, and
  approval of text is not approval of effect.
- **Auto-execute low-risk actions** — deferred: may be revisited for
  read-only or scale-up actions once evaluation data exists, via a new ADR.
