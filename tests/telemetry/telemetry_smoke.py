"""Phase 5 validation: one request can be followed through traces, logs, and metrics.

Runs against the kind cluster (`make deploy-local`) through its published localhost ports:

    make test-telemetry

1. Send a checkout through the storefront with a known trace ID.
2. Tempo holds one trace spanning all five services.
3. Loki holds log lines from storefront and checkout carrying that trace ID.
4. Prometheus has the storefront's request metrics.
5. Ship a payment outage, send another checkout, and confirm the 5xx shows up
   as an error span, an error log line, and an error metric; then roll back.
"""

import contextlib
import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

KUBECTL = ["kubectl", "--context", "kind-opspilot"]
INJECT = str(Path(__file__).resolve().parents[2] / "scripts" / "inject-failure.sh")
SERVICES = {"storefront", "checkout", "payment", "inventory", "notification"}
# Published on localhost by the kind cluster (infrastructure/kind/cluster.yaml).
URLS = {
    "storefront": os.environ.get("STOREFRONT_URL", "http://127.0.0.1:38080"),
    "tempo": os.environ.get("TEMPO_URL", "http://127.0.0.1:33200"),
    "loki": os.environ.get("LOKI_URL", "http://127.0.0.1:33100"),
    "prometheus": os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:39090"),
}


def _up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2).is_success
    except httpx.HTTPError:
        return False


def require(condition: bool, failure: str) -> None:
    if not condition:
        sys.exit(f"FAIL: {failure}")


def wait(check: Callable[[], Any], what: str, timeout: float = 90) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(httpx.HTTPError, KeyError, ValueError):
            if result := check():
                return result
        time.sleep(2)
    sys.exit(f"FAIL: {what} not seen within {timeout:.0f}s")


def checkout(storefront: str) -> tuple[str, int]:
    trace_id = secrets.token_hex(16)
    response = httpx.post(
        f"{storefront}/api/checkout",
        json={"items": [{"sku": "mug", "quantity": 1}]},
        headers={"traceparent": f"00-{trace_id}-{secrets.token_hex(8)}-01"},
        timeout=10,
    )
    return trace_id, response.status_code


def trace_spans(tempo: str, trace_id: str) -> list[tuple[str, dict[str, Any]]]:
    body = httpx.get(f"{tempo}/api/traces/{trace_id}", timeout=5).json()
    spans = []
    for batch in body.get("batches", []):
        resource = {
            a["key"]: a["value"].get("stringValue") for a in batch["resource"]["attributes"]
        }
        for scope in batch.get("scopeSpans", []):
            spans.extend((resource["service.name"], span) for span in scope["spans"])
    return spans


def log_lines(loki: str, trace_id: str) -> list[dict[str, Any]]:
    query = f'{{k8s_namespace_name="demo"}} | trace_id="{trace_id}"'
    now = time.time_ns()
    body = httpx.get(
        f"{loki}/loki/api/v1/query_range",
        params={"query": query, "start": now - 600 * 10**9, "end": now},
        timeout=5,
    ).json()
    return [
        {"service": stream["stream"].get("service_name"), "line": value[1], **stream["stream"]}
        for stream in body["data"]["result"]
        for value in stream["values"]
    ]


def metric(prometheus: str, query: str) -> float:
    result = httpx.get(f"{prometheus}/api/v1/query", params={"query": query}, timeout=5).json()
    values = result["data"]["result"]
    return float(values[0]["value"][1]) if values else 0.0


def kubectl(*args: str) -> None:
    subprocess.run([*KUBECTL, "-n", "demo", *args], check=True, capture_output=True)  # noqa: S603


def main() -> None:
    url = URLS
    ready = [
        f"{url['storefront']}/healthz",
        f"{url['tempo']}/ready",
        f"{url['loki']}/ready",
        f"{url['prometheus']}/-/ready",
    ]
    wait(lambda: all(_up(u) for u in ready), "the published cluster ports", timeout=20)
    trace_id, status = checkout(url["storefront"])
    require(status == 200, f"checkout returned {status}")
    print(f"checkout ok, trace {trace_id}")

    spans = wait(
        lambda: (
            (s := trace_spans(url["tempo"], trace_id)) and {svc for svc, _ in s} == SERVICES and s
        ),
        "a trace across all five services",
    )
    print(f"PASS trace: {len(spans)} spans across {sorted({svc for svc, _ in spans})}")

    lines = wait(
        lambda: (
            (lines := log_lines(url["loki"], trace_id))
            and {"storefront", "checkout"} <= {line["service"] for line in lines}
            and lines
        ),
        "storefront and checkout log lines with the trace ID",
    )
    print(f"PASS logs: {len(lines)} lines carry the trace ID")

    requests = wait(
        lambda: metric(url["prometheus"], 'sum(http_requests_total{service="storefront"})'),
        "storefront request metrics",
    )
    print(f"PASS metrics: storefront has served {requests:.0f} requests")

    errors_before = metric(url["prometheus"], 'sum(http_errors_total{service="payment"})')
    subprocess.run([INJECT, "payment-outage"], check=True)  # noqa: S603 - repository script
    try:
        # Right after the rollout the old payment pod may still be leaving the
        # endpoints, so a request can fail before reaching payment. Send a few
        # and follow the first trace with a failed payment span.
        failed = []
        for _ in range(5):
            trace_id, status = checkout(url["storefront"])
            require(status == 502, f"checkout during the outage returned {status}")
            failed.append(trace_id)
            time.sleep(1)
        failed_trace, errors = wait(
            lambda: next(
                (
                    (tid, errs)
                    for tid in failed
                    if (
                        errs := [
                            span
                            for svc, span in trace_spans(url["tempo"], tid)
                            if svc == "payment"
                            and span.get("status", {}).get("code") == "STATUS_CODE_ERROR"
                        ]
                    )
                ),
                None,
            ),
            "an error span on payment",
        )
        print(f"PASS error trace: {len(errors)} failed payment span(s)")
        wait(
            lambda: any(
                json.loads(line["line"]).get("level") == "error"
                if line["line"].startswith("{")
                else line.get("detected_level") == "error"
                for line in log_lines(url["loki"], failed_trace)
                if line["service"] == "payment"
            ),
            "an error log line from payment with the failed trace ID",
        )
        print("PASS error logs: payment logged the failure under the same trace ID")
        wait(
            lambda: (
                metric(url["prometheus"], 'sum(http_errors_total{service="payment"})')
                > errors_before
            ),
            "payment's error counter increasing",
        )
        print("PASS error metrics: http_errors_total for payment increased")
    finally:
        kubectl("rollout", "undo", "deployment/payment")
        kubectl("rollout", "status", "deployment/payment", "--timeout=2m")
        print("rolled payment back")


if __name__ == "__main__":
    main()
