# Load-test results

k6 scripts in [`tests/performance/k6`](../../tests/performance/k6) against a
locally running API, measured 2026-10-14. Targets (performance plan): authenticated
reads p95 < 300 ms, mutations p95 < 500 ms, error rate < 1 %, live streams
reconnect reliably, and no request waits for the model.

## Environment

| | |
|---|---|
| Host | AMD EPYC 7443P, 48 vCPUs, 62 GiB RAM, NVMe |
| **Host load** | **Shared server, busy with other users' workloads: load average 58-83 during most runs** (one later run on a quiet host, marked below) |
| API | One uvicorn process (`opspilot-api`, as one pod runs it), no reload, `LOG_LEVEL=WARNING`, port 8030 |
| Database | PostgreSQL 17 + pgvector 0.8 (compose container), dedicated database; SQLAlchemy pool 5 + 10 overflow |
| Data | 5 demo services, 6 runbooks, ~1,000 incidents at the start (5,400 incidents, 14,700 timeline events, 38,500 audit rows by the end) |
| Auth | Real Keycloak dev realm tokens (one login in `setup()`, refreshed per VU) |
| k6 | v1.3.0; SSE via the xk6-sse community extension (resolved automatically) |
| Not running | Worker, LLM (investigation requests are only queued) |

The load generator ran on the same host as the API and database, so
absolute numbers are pessimistic; compare runs with each other, not with a
dedicated environment.

## Results

### Reads: `reads.js`, 50 req/s constant arrival, 2 min

Weighted like the UI (incident list 30 %, detail 25 %, timeline 15 %,
services 10 %, topology, metrics, audit log, runbook search 5 % each).

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| **All reads** | **14 ms** | **102 ms** | **401 ms** |
| GET /incidents | 15 ms | 96 ms | 391 ms |
| GET /incidents/{id} | 12 ms | 93 ms | 376 ms |
| GET /incidents/{id}/events | 13 ms | 71 ms | 361 ms |
| GET /services | 12 ms | 86 ms | 411 ms |
| GET /topology | 13 ms | 84 ms | 384 ms |
| GET /incident-metrics | 16 ms | 114 ms | 434 ms |
| GET /audit-logs | 14 ms | 64 ms | 376 ms |
| GET /runbooks/search (embeds the query) | 48 ms | 180 ms | 595 ms |

6,003 requests, 50.0 req/s, **0 errors**. Target met.

### Writes: `writes.js`, 5 incident lifecycles/s (20 mutations/s), 2 min

Each iteration: create incident (Idempotency-Key), acknowledge, edit,
queue an investigation; every mutation also writes timeline and audit rows.

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| **All writes** | **19 ms** | **31 ms** | **36 ms** |
| POST /incidents | 24 ms | 35 ms | 41 ms |
| POST /incidents/{id}/acknowledge | 19 ms | 26 ms | 31 ms |
| PATCH /incidents/{id} | 18 ms | 24 ms | 30 ms |
| POST /incidents/{id}/investigation (agent job) | 18 ms | 24 ms | 28 ms |

2,403 requests, 20.0 req/s, **0 errors**. Queuing an investigation takes
the same time as any write: no request waits for the model. Target met.

### Live streams: `sse.js`, 100 subscribers, writer at 2 lifecycles/s, 2 min

Each client subscribes to the organization stream, listens 20 s,
disconnects, reconnects with `Last-Event-ID`, listens again, then checks
the stored timeline of the incidents it saw for gaps and duplicates.

| | Before the fix | After the fix |
|---|---|---|
| Events delivered | 68,133 | 69,713 |
| Missed / duplicated | 0 / 0 | 0 / 0 |
| Reconnects with Last-Event-ID | 300/300 ok | 300/300 ok |
| Delivery lag p50 / p95 / p99 | 262 / 722 / 1,163 ms | **23 / 125 / 426 ms** |
| Connect time p95 | 1,358 ms | 1,032 ms |

### Sustained mixed load: `mixed.js`, 40 reads/s + 2 lifecycles/s + open streams

| Run | Streams | Host load | Reads p50 / p95 / p99 | Writes p50 / p95 / p99 | Errors |
|---|---|---|---|---|---|
| Before the fix, 10 min | 100 | ~60 | 405 / 3,198 / 5,880 ms | 643 / 3,673 / 7,146 ms | 0 % |
| After the fix, 10 min | 100 | ~60-80 | 34 / 1,271 / 3,428 ms | 54 / 1,483 / 3,815 ms | 0 % |
| After the fix, 3 min | 100 | ~5-12 (quiet) | **13 / 60 / 189 ms** | **26 / 80 / 229 ms** | 0 % |
| After the fix, 3 min | 25 | ~7 (quiet) | **13 / 47 / 122 ms** | **22 / 55 / 117 ms** | 0 % |

About 30,100 requests (48 req/s) and 335,000-349,000 stream events
(530-570 events/s) per 10-minute run; 0 failed requests in every run.

## Bottlenecks found

1. **Live-stream fan-out (fixed).** Every committed event woke every
   subscriber, and each one queried the database and rendered the same
   frames. With 100 organization streams that was 100 identical queries per
   event in one process: delivery lag p95 722 ms and, under mixed load,
   read p95 3.2 s / write p95 3.7 s. Subscribers at the same position now
   share one read and one rendering (single-flight per organization,
   incident, and position). Delivery lag p95 fell to 125 ms; under the same
   host load mixed-load p95 fell 2.5x, and on a quiet host 100 streams plus
   mixed traffic meet the targets (reads 60 ms, writes 80 ms).
2. **One process is CPU-bound with many streams on a busy host.** Even after
   the fix, 100 streams delivering ~570 events/s on a host at load 60-80
   push the tail past the targets. The chart already runs two API replicas
   with an HPA on CPU; streams spread across replicas. Not changed here.
3. **Runbook search** is the slowest read (embedding the query on the CPU,
   p95 180 ms); fine for its 5 % share, worth caching if it becomes hot.

## Reproduce

```bash
make infra-up && make db-upgrade      # PostgreSQL, Redis, Keycloak
(cd apps/api && API_PORT=8030 uv run opspilot-api)   # another shell: one process, no reload
make load-seed API_PORT=8030          # demo services + SEED_INCIDENTS=500 incidents
make test-load API_PORT=8030          # reads, writes, sse, mixed; summaries in test-results/k6/
make test-load API_PORT=8030 K6_TESTS=sse SSE_CLIENTS=100 DURATION=2m
```

Rates and sizes: `READ_RATE`, `WRITE_RATE`, `SSE_CLIENTS`,
`SSE_SESSION_SECONDS`, `DURATION`; thresholds fail the run when a target is
missed (k6 exits non-zero).
