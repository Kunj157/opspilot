"""Feature schema v1: one row per service per 15 s window, read back from Prometheus.

Every feature looks only backwards (rate windows end at the row's time), so a
row never contains information from after its timestamp. CPU and memory are
not part of v1: the kind demo cluster runs no cAdvisor scrape.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

SCHEMA_VERSION = "v1"
STEP = timedelta(seconds=15)
NAMESPACE = "demo"
# The synthetic traffic source reports metrics too; it is not a monitored service.
EXCLUDED_SERVICES = frozenset({"loadgen"})
FEATURES = [
    "request_rate",
    "error_rate",
    "p50_seconds",
    "p95_seconds",
    "p99_seconds",
    "restarts_5m",
    "availability",
]
# What a missing value means: no traffic → no errors and no latency; no
# kube-state sample → assume nothing restarted and the deployment is available.
FILL = {
    "request_rate": 0.0,
    "error_rate": 0.0,
    "p50_seconds": 0.0,
    "p95_seconds": 0.0,
    "p99_seconds": 0.0,
    "restarts_5m": 0.0,
    "availability": 1.0,
}


def _http(metric: str) -> str:
    return f'{metric}{{namespace="{NAMESPACE}"}}'


def _quantile(q: float) -> str:
    return (
        f"histogram_quantile({q}, sum by (service, le) "
        f"(rate({_http('http_request_duration_seconds_bucket')}[1m])))"
    )


QUERIES = {
    "request_rate": f"sum by (service) (rate({_http('http_requests_total')}[1m]))",
    "error_rate": (
        f"sum by (service) (rate({_http('http_errors_total')}[1m])) "
        f"/ sum by (service) (rate({_http('http_requests_total')}[1m]))"
    ),
    "p50_seconds": _quantile(0.5),
    "p95_seconds": _quantile(0.95),
    "p99_seconds": _quantile(0.99),
    "restarts_5m": (
        "sum by (service) (label_replace(increase(kube_pod_container_status_restarts_total{"
        f'namespace="{NAMESPACE}"}}[5m]), "service", "$1", "container", "(.*)"))'
    ),
    "availability": (
        'label_replace(kube_deployment_status_replicas_available{namespace="'
        f'{NAMESPACE}"}} / kube_deployment_spec_replicas{{namespace="{NAMESPACE}"}}, '
        '"service", "$1", "deployment", "(.*)")'
    ),
}


@dataclass(frozen=True)
class Run:
    """One labelled scenario run (a line of datasets/runs.jsonl)."""

    scenario: str
    service: str
    rps: int
    stable_start: datetime
    fault_start: datetime
    fault_end: datetime
    recovered_at: datetime

    @classmethod
    def parse(cls, line: str) -> "Run":
        raw = json.loads(line)
        return cls(
            scenario=raw["scenario"],
            service=raw["service"],
            rps=int(raw["rps"]),
            **{
                k: datetime.fromisoformat(raw[k])
                for k in ("stable_start", "fault_start", "fault_end", "recovered_at")
            },
        )


def load_runs(path: Path) -> list[Run]:
    return [Run.parse(line) for line in path.read_text().splitlines() if line.strip()]


def query_range(
    client: httpx.Client, promql: str, start: datetime, end: datetime
) -> dict[str, pd.Series]:
    """Series per service label for one query."""
    response = client.get(
        "/api/v1/query_range",
        params={
            "query": promql,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": STEP.total_seconds(),
        },
    )
    response.raise_for_status()
    out: dict[str, pd.Series] = {}
    for result in response.json()["data"]["result"]:
        service = result["metric"].get("service")
        if not service:
            continue
        times = pd.to_datetime([float(t) for t, _ in result["values"]], unit="s", utc=True)
        values = pd.to_numeric([v for _, v in result["values"]], errors="coerce")
        out[service] = pd.Series(values, index=times, dtype=float)
    return out


def fetch(prometheus_url: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Raw feature frame (service, time, features) for a period, missing values kept as NaN."""
    frames = []
    with httpx.Client(base_url=prometheus_url, timeout=60) as client:
        per_feature = {name: query_range(client, q, start, end) for name, q in QUERIES.items()}
    services = sorted({s for series in per_feature.values() for s in series} - EXCLUDED_SERVICES)
    for service in services:
        columns = {
            name: per_feature[name].get(service, pd.Series(dtype=float)) for name in FEATURES
        }
        frame = pd.DataFrame(columns)
        frame.index.name = "time"
        frame["service"] = service
        frames.append(frame.reset_index())
    if not frames:
        return pd.DataFrame(columns=["time", "service", *FEATURES])
    return pd.concat(frames, ignore_index=True).sort_values(["time", "service"])


def clean(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the schema and fill missing values with their documented meaning."""
    missing = [c for c in ["time", "service", *FEATURES] if c not in frame.columns]
    if missing:
        raise ValueError(f"feature frame lacks {missing} (schema {SCHEMA_VERSION})")
    out = frame.copy()
    for name in FEATURES:
        values = pd.to_numeric(out[name], errors="coerce").replace([np.inf, -np.inf], np.nan)
        out[name] = values.fillna(FILL[name]).astype(float)
    out["error_rate"] = out["error_rate"].clip(0.0, 1.0)
    out["availability"] = out["availability"].clip(0.0, 1.0)
    return out.reset_index(drop=True)


# After a rollback the healthy release is still rolling out for a while.
RECOVERY = timedelta(minutes=2)


def label(frame: pd.DataFrame, runs: Iterable[Run]) -> pd.DataFrame:
    """Add `anomaly`, `fault_active`, and the owning `run`.

    `anomaly` marks the faulty service while its faulty release is live.
    `fault_active` marks every service from fault start until the recovery
    has settled: callers of the faulty service really do fail then, so those
    windows are neither normal (for training) nor false alerts (for scoring).
    """
    out = frame.copy()
    out["anomaly"] = 0
    out["fault_active"] = 0
    out["run"] = -1
    for i, run in enumerate(runs):
        in_run = (out["time"] >= run.stable_start) & (out["time"] <= run.recovered_at)
        out.loc[in_run, "run"] = i
        active = (out["time"] >= run.fault_start) & (out["time"] < run.fault_end + RECOVERY)
        out.loc[in_run & active, "fault_active"] = 1
        faulty = (
            in_run
            & (out["service"] == run.service)
            & (out["time"] >= run.fault_start)
            & (out["time"] < run.fault_end)
        )
        out.loc[faulty, "anomaly"] = 1
    return out


def build(prometheus_url: str, runs: list[Run]) -> pd.DataFrame:
    """The labelled dataset for all runs, each run read separately and numbered in order."""
    frames = []
    for i, run in enumerate(runs):
        frame = label(clean(fetch(prometheus_url, run.stable_start, run.recovered_at)), [run])
        frame["run"] = i
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)
