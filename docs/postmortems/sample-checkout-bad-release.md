# Sample postmortem: checkout release 1.4.2 returned 500s

> **This is a sample.** It shows the shape of the postmortem OpsPilot drafts
> for the repository's demo incident (`checkout-http-500`, see
> [failure injection](../../demo/failure-injection/README.md)). The incident
> happened in the demo shop, not in production. The error rates come from the
> agent-evaluation case `checkout-bad-release`
> (`tests/agent-evals/investigations.json`) and the measured demo run in the
> failure-injection README. Offsets from detection are illustrative, not
> measurements; no real customer or money was affected. Real postmortems are
> generated per incident at `/incidents/<id>` and stored with the evidence
> they cite.

| | |
|---|---|
| Service | `checkout` (namespace `demo`), with `storefront` degraded downstream |
| Severity | High: customers could not complete purchases |
| Status | Resolved by an approved rollback |
| Drafted by | OpsPilot postmortem agent, from the incident record; edited for this sample |
| Format | Blameless. Every finding is labelled and cites evidence. |

## Summary

Checkout release 1.4.2 (revision 19) was deployed with a fault that made about
half of checkout requests fail with HTTP 500. Storefront checkouts, which call
checkout, returned 502. The detector opened one incident after the error rate
stayed above 5% for three evaluation windows. The investigation tied the start
of the errors to the new revision, and an incident commander approved a
rollback to revision 18. After the rollback the error rate stayed below 2% for
three windows and the incident was resolved.

## Impact

- Checkout error rate rose from 0% to 31% (first reading in the investigation)
  and reached 54% in the measured demo run; storefront rose from 0% to 18%
  (14% in the demo run).
- Browsing (`/api/products`) kept working. Only purchases failed.

## Timeline

Taken from the incident events and audit log, never written by the model.
Offsets are from the moment the faulty release was applied.

| Offset | Event | Actor |
|---|---|---|
| T+0 | Revision 19 (`checkout 1.4.2`, commit `cf7db1a`, PR #142, "retry orders on provider errors") rolled out | CI / `kubectl` |
| T+1 min | Checkout error rate crosses 5% with enough traffic; first window counted | Detector |
| T+3 min | Third consecutive window above threshold; incident opened, severity set, service turned red on the topology | Detector |
| T+3 min | Investigation started: metrics, logs, traces, deployments, commit metadata, runbooks | Investigation agents |
| T+4 min | Root-cause hypothesis recorded with citations; rollback proposed against evidence E1 to E6 | Remediation agent |
| T+6 min | Rollback approved for that exact proposal version | Incident commander |
| T+6 min | `ROLLBACK_DEPLOYMENT` on `checkout` executed once (allow-listed namespace `demo`) | Worker |
| T+9 min | Error rate below 2% for three consecutive windows, compared with the pre-incident baseline; incident resolved | Verification worker |
| T+10 min | Postmortem drafted | Postmortem agent |

## Evidence

| Ref | Source | Summary |
|---|---|---|
| E1 | Prometheus | `checkout` error rate 0.31 now, 0.0 before the incident |
| E2 | Prometheus | `storefront` error rate 0.18 now, 0.0 before |
| E3 | Loki | 14 error logs on `checkout`: "order failed (/orders, status 500)" |
| E4 | Tempo | Failing span on `POST /orders` in `checkout` |
| E5 | Kubernetes | Revision 19 created 5 minutes before detection; revision 18 was live for 24 hours; `SERVICE_VERSION` 1.4.2, fault setting present |
| E6 | Deployment metadata | Commit `cf7db1a`, "checkout 1.4.2: retry orders on provider errors", PR #142 |
| E7 | Runbook | `checkout-high-error-rate`, `deployment-rollback` |

## Root cause

**Strong hypothesis.** The release 1.4.2 change in `checkout` introduced the
regression. Evidence: the errors start with revision 19 (E5), the only change
in the window is that release (E5, E6), and the failing span is inside
`checkout` itself rather than a dependency (E4).

## Findings

| Certainty | Finding | Evidence |
|---|---|---|
| Confirmed | Checkout error rate rose from 0 to 31% | E1 |
| Confirmed | Storefront checkouts failed with 502 because checkout failed | E2, E3 |
| Confirmed | The errors began after revision 19 was rolled out | E1, E5 |
| Strong hypothesis | The change in PR #142 caused the 500s | E4, E5, E6 |
| Weak hypothesis | The retry logic in the PR amplified load on dependencies | E6 |
| Unknown | Why the change passed review and pre-release checks | none |

## Resolution

Rollback of `checkout` to revision 18 through the allow-listed
`ROLLBACK_DEPLOYMENT` action, approved by an incident commander and executed
once. Recovery was verified against the pre-incident baseline before the
incident was resolved.

## Follow-up actions

1. Add a canary stage or progressive rollout for `checkout` so a bad release
   reaches a fraction of traffic first.
2. Alert on error rate per revision, not only per service.
3. Add a test for the retry-on-provider-error path in PR #142's area.
4. Investigate the unknown above in the release review, and record the answer
   here.
5. Re-run the investigation against a real model (`make test-agent
   LLM=ollama`) before relying on weak hypotheses such as the retry
   amplification.

## What went well

- Exactly one incident was opened; the detector's cooldown prevented
  duplicates.
- The proposal cited its evidence, and the approval was bound to that exact
  proposal version.
- The rollback ran once, and resolution waited for verified recovery.

## What to improve

- Detection waits for three windows by design; a faster signal for a
  100%-failing release would shorten the impact.
