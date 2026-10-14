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
