# Chaos test results

Fault-injection suite in [`tests/chaos`](../../tests/chaos), run with
`make test-chaos` (Docker required; about 2 minutes). Each scenario uses
real containers (Testcontainers) or real processes and injects the fault
the way it happens in production: containers are stopped, paused, or
restarted; the API and worker are SIGKILLed; the model and Kubernetes API
are replaced by local servers that fail or never answer. Results from
2026-10-14 on the shared development host.

| # | Scenario | How the fault is injected | Expected behaviour (asserted) | Result |
|---|---|---|---|---|
| 1 | Redis down | `docker stop` the Redis container, then start it | `/ready` answers 503 with `redis: fail` within its 1 s per-check timeout, database still `ok`; reads and writes keep returning 200/201; readiness recovers after the restart | Pass |
| 2 | Redpanda down | `docker pause` the broker during publishing, unpause | The relay fails (bounded by the producer timeout), its checkpoint stays at the last acknowledged event; events written during the outage stay in the outbox; after unpause the relay resumes and every event reaches the topic; redelivered messages are handled once per consumer (dedupe by event ID) | Pass |
| 3 | API restart mid-SSE | SIGKILL the API process (`python -m opspilot_api`) while a client streams an incident; the worker writes 5 timeline entries while it is down; start it again | The client reconnects with `Last-Event-ID`, receives the missed entries, and ends with exactly the stored timeline: no gaps, no duplicates, in order; two connections in total | Pass |
| 4 | Worker killed mid-investigation | SIGKILL a worker process after it persisted a node past triage | The job stays `running` under its lease; a live worker does not steal it; after the lease expires (fast-forwarded) another worker resumes from the persisted node and completes it; one `investigation_finished` event, no duplicate evidence, triage not redone, attempts = 2 | Pass |
| 5a | LLM 5xx storm | Model endpoint answers 503 to everything | Each model call is tried exactly 3 times; the investigation ends `partial` with manual review, keeps its tool evidence, in about 1 s | Pass |
| 5b | LLM timeout storm | Model endpoint never answers in time (0.5 s client timeout) | Same as 5a, bounded by attempts x timeout (about 9 s for the whole investigation) | Pass |
| 5c | Slow model vs. lease | Model calls take 3 x 0.8 s, longer than a 2 s lease; a second worker polls | The second worker never takes over the running job (lease renewed); attempts = 1 | **Failed before the fix**, pass after |
| 6 | Kubernetes API timeout during remediation | A fake API server accepts every PATCH and never answers | Each attempt gives up after the request timeout; 3 attempts send the identical patch (same `restartedAt`), strictly one after another; then the execution fails safe: `failed`, `remediation.failed` audit record, incident reopened for a new investigation | **Could not be bounded before the fix**, pass after |
| 7 | PostgreSQL restart | `docker stop` / `docker start` the database with a warm pool | While down: `/ready` 503 and API requests answer 503 with `Retry-After` within 5 s (no hang); after the restart: 20/20 concurrent requests succeed on the first try (pool pre-ping replaces dead connections), writes work | **500 instead of 503 before the fix**, pass after |

## Resilience bugs found and fixed

1. **Second worker could run a live investigation** (scenario 5c). The
   investigation lease (10 min) was never renewed, while one investigation
   could take 6 calls x 3 attempts x 120 s of model time. The runner now
   renews the lease every third of its length and stops if it lost the job.
   The configured `LLM_TIMEOUT_SECONDS` was also never applied (always
   120 s); it is now. (PR #346)
2. **No timeout on Kubernetes API calls** (scenario 6). The official client
   has no default timeout, so a silent API server blocked the worker thread
   forever and the remediation lease (5 min) could expire with the write
   still in flight. Every call now has `KUBERNETES_REQUEST_TIMEOUT_SECONDS`
   (30 s). (PR #345)
3. **Database outage answered 500** (scenario 7). Connection errors now
   answer 503 with `Retry-After`, without connection details. (PR #344)

Found by the load tests rather than the chaos suite: live-stream fan-out
(one query per subscriber per event), fixed in PR #336.

## Observations (no change needed)

- Redis is only a readiness dependency today, so an outage marks pods not
  ready without affecting requests. With several replicas all reporting
  not-ready at once, Kubernetes would take every API pod out of service; if
  Redis stays optional on the request path, consider dropping it from
  readiness (or making it a degraded, non-failing check).
- A broker pause makes one relay iteration wait for the producer's request
  timeout (10 s, up to about a minute with retries); nothing is lost, the
  outbox alert (`OpsPilotEventOutboxBacklog`) covers a long outage.
- Live streams read `sequence > last` (as does the relay, which waits for a
  settle delay). Under heavy concurrent writes a lower sequence committed
  after a higher one could be skipped by a stream; no such loss appeared in
  the load tests (0 missed of 69,713 events) or here.

## Not covered

- Real Kubernetes failure modes (node loss, API server failover) and Chaos
  Mesh experiments: the shared host has no spare cluster capacity.
- Network partitions with packet loss or latency (would need `tc`/toxiproxy).
- PostgreSQL failover to a replica (single instance locally).
