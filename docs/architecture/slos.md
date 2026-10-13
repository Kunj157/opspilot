# Service Level Objectives

Initial SLOs from `DEVELOPMENT_PLAN.md` §26, made measurable. Each SLI names
the signal that will compute it once the corresponding phase lands. Targets
are for a portfolio demo environment, not a commercial commitment.

| # | SLO | Target | SLI (how it is measured) | Window | Measurable from |
|---|---|---|---|---|---|
| 1 | API availability | 99.5% | `sum(rate(http_requests_total{service="api",code!~"5.."}))` / `sum(rate(http_requests_total{service="api"}))` | 30 days rolling | Phase 1 |
| 2 | API latency | 95% of non-agent requests < 500 ms | `histogram_quantile(0.95, http_request_duration_seconds{service="api",route!~".*/stream"})` | 30 days rolling | Phase 1 |
| 3 | API read latency under load | P95 < 300 ms | k6 load-test report (`tests/performance/`) | Per release | Phase 3 |
| 4 | Detection | 95% of supported injected failures detected within 120 s | `incident.started_at − injection timestamp` from the failure-injection suite | Per release | Phase 6 |
| 5 | Investigation quality | 90% of evaluation incidents produce a valid, evidence-backed investigation | Agent eval suite pass rate (`tests/agent-evals/`) | Per release | Phase 8 |
| 6 | Remediation safety | 100% of mutating remediations have a valid approval; 0 arbitrary shell commands | Audit-log query: executions without matching approval = 0; adapter has no shell method | Continuous | Phase 9 |
| 7 | Event processing | 99% of events processed within 60 s | Consumer lag and `event_processing_duration_seconds` | 30 days rolling | Phase 11 |

## Error budgets

- **API availability 99.5% over 30 days** ≈ 3 h 36 min of failed-request
  equivalent per month.
- When a budget is exhausted, feature work stops and the next PRs go to
  reliability fixes until the burn rate is back under 1×.

## Alerting (burn-rate based)

| Alert | Condition | Severity |
|---|---|---|
| Fast burn | Availability error budget burning at 14.4× over 1 h **and** 5 m | page |
| Slow burn | Burning at 6× over 6 h **and** 30 m | ticket |
| Detection worker stopped | No detector heartbeat for 5 m | page |
| Remediation without approval | Any audit record violating SLO 6 | page |

The remaining required alerts (plan §26) are defined alongside the
components that emit their signals.

## Review

SLO targets are reviewed at the end of each phase. Changes are made in a
`docs/*` PR with the measured data that justifies them.
