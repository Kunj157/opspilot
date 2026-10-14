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

## Component alerts

### OpsPilotAPIErrorRateHigh

More than 5 % of API requests returned 5xx for 5 minutes (with at least
0.1 req/s, so an idle API cannot page). Triage exactly as
[the fast burn](#opspilotapiavailabilityfastburn); this alert reacts sooner
to a sudden jump, the burn alert to sustained loss.

### OpsPilotAPILatencyHigh

API p95 above 500 ms for 10 minutes (stream routes excluded). Triage as
[the latency burn](#opspilotapilatencyfastburn).

### OpsPilotDatabasePoolExhausted

A process has more than 90 % of its SQLAlchemy pool (size + overflow)
checked out for 5 minutes. Requests then queue for a connection and fail
after the pool timeout.

1. Which process? The `pool` label (`api` or `worker`) and `pod`.
2. Long transactions: `select pid, state, now() - xact_start as age, query from pg_stat_activity where datname = 'opspilot' order by age desc limit 20;`
3. Mitigate: restart the pod holding the connections; if every API replica
   is saturated by real load, scale the API out only as far as PostgreSQL's
   `max_connections` allows (each replica opens up to 15).
4. See also the [database connection exhaustion runbook](../runbooks/database-connection-exhaustion.md).

### OpsPilotWorkerQueueBacklog

The oldest queued investigation or approved remediation has waited over 10
minutes. Approved remediations should start within seconds.

1. Is the worker running? `kubectl -n opspilot get pods -l app.kubernetes.io/name=opspilot-worker`.
2. Worker logs for `worker iteration failed`; a crash loop or an
   unreachable database stops every loop.
3. A stuck investigation holds its lease for up to 10 minutes and is then
   taken over; restarting the worker is safe (leases and idempotency keys).

### OpsPilotConsumerLagHigh

An event consumer group is more than 500 messages behind for 10 minutes.
Check the worker is running and not failing handlers (worker logs,
`opspilot_events_handled_total` by outcome). Lag clears by itself once the
consumer is healthy; handlers are idempotent.

### OpsPilotEventOutboxBacklog

More than 1000 timeline events are waiting for the relay for 10 minutes,
usually because Redpanda is unreachable. Nothing is lost: the relay resumes
at its checkpoint. Restore the broker (`kubectl -n opspilot get pods` for
the Redpanda pod, or the managed cluster's status) and watch the depth fall.

### OpsPilotDeadLetterMessages

A consumer parked messages on a `<topic>.dlq` topic (poison message, unknown
version, or a handler that failed four times).

1. Read the parked message and its `error` header:
   `rpk topic consume incident.created.v1.dlq -n 5`.
2. Fix the cause (a bug or a bad producer), then replay:
   `python -m opspilot_api.events replay --topic incident.created.v1 --from-dlq`.
   Replays are idempotent per consumer and event ID.

### OpsPilotAgentFailureRateHigh

More than 25 % of investigations in the last hour crashed or gave up after
three attempts (at least four runs). Partial results are not counted.

1. Model availability: `opspilot_llm_requests_total{outcome="error"}`; for
   Ollama check the GPU node and `ollama ps`, for a hosted model its status
   page and our API key.
2. Telemetry backends: the tools read Prometheus, Loki, and Tempo; worker
   logs show which tool failed.
3. Incidents stay in `investigating` with manual review recommended;
   responders can investigate by hand meanwhile.

### OpsPilotLLMCostBudgetBreach

Estimated LLM spend over the last 24 hours exceeded `LLM_DAILY_BUDGET_USD`
(page), or passed 80 % of it (ticket). Each investigation is capped by its
own cost limit, so this means many investigations, not one runaway.

1. `sum by (model) (increase(opspilot_llm_cost_usd_total[24h]))` and the
   number of investigations created today: a detector flapping?
2. Mitigate: switch to the local model (`LLM_PROVIDER=ollama`) or set
   `AUTO_INVESTIGATE=false` until the cause is fixed.

### OpsPilotDetectionWorkerStopped

No detection cycle for 10 minutes (or the worker exports no metrics at
all), or most cycles cannot read Prometheus
(`OpsPilotDetectionTelemetryUnavailable`). Failures in the monitored
services are not being detected.

1. Worker pod running and its `/metrics` scraped (`up` for the worker pod)?
2. `PROMETHEUS_URL` reachable from the worker: logs show
   `telemetry_unavailable` cycles.
3. Restart the worker; detection resumes on the next cycle.

### OpsPilotRemediationFailed

An approved remediation failed (Kubernetes rejected it, a precondition no
longer held, or transient errors exhausted its retries). The incident was
reopened and a new investigation queued.

1. Incident timeline: the `Remediation failed: ...` entry carries the error.
2. The service may still be degraded: act by hand if needed
   (`kubectl rollout undo deploy/<name> -n <namespace>`), and record it on
   the incident.
3. RBAC errors mean the worker's Role in the target namespace is missing a
   verb; check `kubectl auth can-i patch deployments --as=system:serviceaccount:opspilot:opspilot-worker -n demo`.

### OpsPilotBackupFailed

A backup job failed (ticket), or no backup has succeeded for 26 hours
(`OpsPilotBackupStale`, page; the RPO target is 24 h).

1. `kubectl -n opspilot get jobs -l app.kubernetes.io/name=opspilot-db-backup`
   and the failed job's logs.
2. Typical causes: database credentials rotated, the bucket or PVC full or
   unreachable, the job's deadline too short for the database size.
3. Run one now: `kubectl -n opspilot create job --from=cronjob/opspilot-db-backup backup-manual`.
4. Restores: see the disaster-recovery runbook in this directory.

### OpsPilotCertificateExpiringSoon

A certificate (cert-manager `Certificate` or a TLS endpoint probed by the
blackbox exporter) expires within 14 days (ticket) or 3 days
(`OpsPilotCertificateExpiryImminent`, page). cert-manager renews at 30 days,
so renewal is failing.

1. `kubectl describe certificate -A` and `kubectl get certificaterequests,orders,challenges -A`.
2. Usual causes: ACME challenge not reachable (DNS, ingress), rate limits,
   or an issuer credential problem.
3. Force a renewal after fixing: `cmctl renew <name> -n <namespace>`.
