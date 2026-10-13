# Observability stack (local)

`make deploy-local` deploys this stack to the kind cluster (namespace
`observability`) before the demo shop. Manifests are in `k8s/` and applied
with `kubectl apply -k`.

| Component | Role |
|---|---|
| OpenTelemetry Collector (DaemonSet) | Receives OTLP traces from the demo services; tails demo pod logs, lifts `trace_id`/`span_id`/level out of the JSON lines |
| Tempo | Trace storage (`tempo:3200`, OTLP gRPC `tempo:4317`) |
| Loki | Log storage over OTLP; `service_name` and `k8s_namespace_name` are labels, `trace_id` is structured metadata |
| Prometheus | Scrapes pods annotated `prometheus.io/scrape` and kube-state-metrics |
| kube-state-metrics | `kube_pod_container_status_restarts_total`, `kube_deployment_status_replicas_available` |
| Grafana | Provisioned datasources (log lines link to their trace, traces link to their logs) and the **Demo shop** dashboard |

Grafana is on http://localhost:33300 (anonymous, read-only), Prometheus on
:39090, Loki on :33100, and Tempo on :33200; the kind cluster maps these to
NodePort services. The admin password is generated into the
`grafana-admin` Secret on first deploy:

```bash
kubectl --kubeconfig .kube/config -n observability get secret grafana-admin \
  -o jsonpath='{.data.password}' | base64 -d
```

Data lives in `emptyDir` volumes and is lost when pods restart; this stack
is for local development and the demo, not production.
