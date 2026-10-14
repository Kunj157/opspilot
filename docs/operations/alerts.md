# Alert runbook

Every OpsPilot alert links here (`runbook_url`). Rules live in
[`observability/k8s/rules/opspilot-alerts.yaml`](../../observability/k8s/rules/opspilot-alerts.yaml)
and are unit-tested with `make test-alerts`; SLO targets and error budgets
are defined in [the SLO document](../architecture/slos.md).

Severities: **page** needs a human now; **ticket** is handled in working
hours. Each section says what the alert means, what to look at first, and
how to stop the bleeding. Fix the cause afterwards in a normal PR.

Useful everywhere:

- API and worker logs: Grafana → Explore → Loki, `{namespace="opspilot"}`;
  filter by `request_id` or `incident_id`.
- Readiness: `kubectl -n opspilot exec deploy/opspilot-api -- curl -s localhost:8000/api/v1/ready`
  lists each dependency as `ok`/`fail`.
- Recent releases: `kubectl -n opspilot rollout history deploy/opspilot-api`.

## SLO burn-rate alerts

Multi-window burn rates (the long window proves it is real, the short one
that it is still happening). A fast burn spends 2 % of the 30-day budget
per hour; a slow burn 5 % per 6 hours.

### OpsPilotAPIAvailabilityFastBurn

More than 7.2 % of API requests return 5xx over both 1 h and 5 m.

1. `sum by (route, status) (rate(http_requests_total{service="opspilot-api",status=~"5.."}[5m]))`
   tells you whether it is one route or all of them.
2. All routes: check `/api/v1/ready`. A failing `database` check means
   PostgreSQL ([OpsPilotDatabasePoolExhausted](#opspilotdatabasepoolexhausted));
   a failing `redis` check alone should not cause 5xx, so keep looking.
3. Started with a deploy: roll back
   (`kubectl argo rollouts undo opspilot-api -n opspilot`, or
   `kubectl rollout undo deploy/opspilot-api -n opspilot`).

### OpsPilotAPIAvailabilitySlowBurn

More than 3 % of requests failed over 6 h and 30 m. Same triage as the fast
burn; usually one flaky route or dependency. Open an issue with the route
breakdown.

### OpsPilotAPILatencyFastBurn

More than 72 % of non-streaming requests take over 500 ms (1 h and 5 m).

1. `histogram_quantile(0.95, sum by (le, route) (rate(http_request_duration_seconds_bucket{service="opspilot-api",route!~".*/stream"}[5m])))`
   finds the slow routes.
2. CPU throttling: `rate(container_cpu_cfs_throttled_seconds_total{namespace="opspilot"}[5m])`;
   scale out (`kubectl -n opspilot scale deploy/opspilot-api --replicas=4`)
   if the HPA is already at its maximum.
3. Database: pool saturation (see below) or slow queries in the PostgreSQL
   logs.

### OpsPilotAPILatencySlowBurn

More than 30 % of requests took over 500 ms for 6 h. Triage as above; often
a missing index on a growing table. Compare with the latest load-test report
in `docs/performance/`.

### OpsPilotEventProcessingBudgetBurn

More than 14.4 % of events took over 60 s from occurring to being handled.

1. Consumer lag: `opspilot_consumer_lag` by topic; is the worker running?
2. Handler errors: worker logs for `opspilot.events.consumer`, and
   [OpsPilotDeadLetterMessages](#opspilotdeadlettermessages).
3. Outbox backlog: `opspilot_queue_depth{queue="event_outbox"}`; if it grows,
   the relay cannot reach Redpanda.

### OpsPilotRemediationWithoutApproval

The executor's pre-execution recheck refused an action because it had no
approval. The guard worked, but something queued an unapproved execution,
which breaks the remediation-safety SLO.

1. Stop the worker's remediation loop until understood:
   `kubectl -n opspilot scale deploy/opspilot-worker --replicas=0`.
2. Find the execution: audit log entries `remediation.failed` with error
   "the proposal has no approval".
3. Treat it as a security incident: who or what created the execution row?
