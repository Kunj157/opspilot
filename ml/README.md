# ML anomaly detection

Labelled failure data from the demo cluster, two detectors on the same
features, and their evaluation.

```bash
make ml-scenarios     # labelled failure runs on the kind demo (≈13 min each)
make ml-dataset       # feature windows read back from Prometheus
make ml-train         # train, evaluate, track in MLflow, write the report
make test-ml          # schema, missing values, leakage, determinism, artifacts
```

## Data

`pipelines/run_scenarios.py` runs each scenario from
`demo/failure-injection` the same way: reset the demo, set the traffic rate,
5 minutes of stable traffic, ship the faulty release, hold it for 4 minutes,
roll back, record 3 minutes of recovery. Each run's labels go to
`datasets/runs.jsonl`.

`pipelines/build_dataset.py` reads each run back from Prometheus as 15 s
windows per service (feature schema **v1**):

| Feature | Source |
|---|---|
| `request_rate` | `rate(http_requests_total[1m])` |
| `error_rate` | errors / requests over 1 m |
| `p50/p95/p99_seconds` | request duration histogram over 1 m |
| `restarts_5m` | kube-state-metrics container restarts over 5 m |
| `availability` | available / desired replicas |

Each feature looks only backwards. Missing values have a fixed meaning:
no traffic means no errors and no latency, and no kube-state sample means no
restarts and full availability. CPU and memory are not in v1 because the kind
cluster has no cAdvisor scrape. A window is labelled anomalous for the faulty
service while its faulty release is live.

## Results (feature schema v1)

Seven runs recorded on the kind demo: every scenario once, plus checkout
errors and checkout latency at a second traffic rate. 1,785 windows, 121 of
them anomalous. The last two runs in time (checkout errors at 8 req/s,
checkout latency at 6 req/s) are held out whole for testing. Full report:
`evaluation/report-v1.json`.

| Held-out runs | Rolling z-score (baseline) | Isolation Forest |
|---|---|---|
| Precision | 1.00 | 0.94 |
| Recall | 0.94 | 0.46 |
| F1 | 0.97 | 0.62 |
| False alerts per hour | 0.0 | 2.3 |
| Median detection delay | 23 s | 23 s |
| Missed incidents | 0 of 2 | 1 of 2 |
| Inference per window | 0.45 ms | 0.44 ms |

On this data the robust rolling z-score is the better detector, and the
promotion rule (beat or complement the baseline, at most one false alert per
hour) correctly keeps the Isolation Forest out of production. It can still
run in shadow mode for comparison. Both detectors alert in about 23 s, where
the production error-rate rule needs about 60 s, because they look at
deviation from each service's own recent behaviour rather than a fixed
threshold.

Two labelling decisions matter. While a service fails, its callers fail too.
Those windows, and the two minutes of recovery after a rollback, are neither
used as normal training data nor counted as false alerts (`fault_active`).
Before this was done, both detectors looked much worse (baseline precision
0.47) for alerts that were in fact real impact.

Limits: seven runs on a single machine is a small dataset. The Isolation
Forest might do better with more varied normal traffic (deploys, load
spikes, and slow drifts that the baseline over-reacts to), which this demo
does not generate yet.
