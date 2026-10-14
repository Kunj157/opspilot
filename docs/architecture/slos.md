# Service Level Objectives

Initial SLOs, made measurable. Each SLI names
the signal that will compute it once the corresponding phase lands. Targets
are for a portfolio demo environment, not a commercial commitment.

| # | SLO | Target | SLI (how it is measured) | Window | Measurable from |
|---|---|---|---|---|---|
| 1 | API availability | 99.5% | `1 - slo:api_errors:ratio_rate*` = non-5xx share of `http_requests_total{service="opspilot-api"}` | 30 days rolling | Phase 1 |
| 2 | API latency | 95% of non-agent requests < 500 ms | `1 - slo:api_slow_requests:ratio_rate*` = share of `http_request_duration_seconds{service="opspilot-api",route!~".*/stream"}` within 0.5 s | 30 days rolling | Phase 1 |
| 3 | API read latency under load | P95 < 300 ms | k6 load-test report (`tests/performance/`) | Per release | Phase 3 |
| 4 | Detection | 95% of supported injected failures detected within 120 s | `incident.started_at − injection timestamp` from the failure-injection suite | Per release | Phase 6 |
| 5 | Investigation quality | 90% of evaluation incidents produce a valid, evidence-backed investigation | Agent eval suite pass rate (`tests/agent-evals/`) | Per release | Phase 8 |
| 6 | Remediation safety | 100% of mutating remediations have a valid approval; 0 arbitrary shell commands | Audit-log query: executions without matching approval = 0; adapter has no shell method | Continuous | Phase 9 |
| 7 | Event processing | 99% of events processed within 60 s | `opspilot_event_processing_delay_seconds` (`slo:event_slow:ratio_rate*`) and consumer lag | 30 days rolling | Phase 11 |

## Error budgets

- **API availability 99.5% over 30 days** ≈ 3 h 36 min of failed-request
  equivalent per month.
- When a budget is exhausted, feature work stops and the next PRs go to
  reliability fixes until the burn rate is back under 1×.

## Alerting (burn-rate based)

Rules: `observability/k8s/rules/opspilot-alerts.yaml` (unit-tested with
`make test-alerts`); what to do when one fires: [the alert runbook](../operations/alerts.md).

| Alert | Condition | Severity |
|---|---|---|
| Availability fast burn | Error budget burning at 14.4× over 1 h **and** 5 m | page |
| Availability slow burn | Burning at 6× over 6 h **and** 30 m | ticket |
| Latency fast / slow burn | Same windows against the 5 % slow-request budget | page / ticket |
| Event processing burn | 14.4× over 1 h and 5 m against the 1 % budget | page |
| Remediation without approval | The executor refused an unapproved action (SLO 6) | page |

The remaining required alerts (plan §26) are listed in the alert runbook.

## Review

SLO targets are reviewed at the end of each phase. Changes are made in a
`docs/*` PR with the measured data that justifies them.
