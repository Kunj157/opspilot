"""Generate labelled failure runs on the local demo cluster.

    uv run --directory ml python pipelines/run_scenarios.py [--plan default]

For every run: reset the demo, set the traffic rate, record a stable window,
ship one faulty release, hold it, roll back, and record the recovery. Each
run's labels (fault start and end, recovery, service, scenario, traffic) are
appended to datasets/runs.jsonl. Telemetry stays in Prometheus; the feature
pipeline reads it back for the labelled windows.
"""

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "ml" / "datasets" / "runs.jsonl"
CATALOG = ROOT / "demo" / "failure-injection" / "scenarios.env"

# (scenario, requests per second): every scenario once, the common ones at
# a second traffic level, so the model sees the same failure at other rates.
PLANS = {
    "default": [
        ("checkout-http-500", 5),
        ("checkout-latency", 3),
        ("payment-timeout", 5),
        ("inventory-http-500", 8),
        ("payment-outage", 4),
        ("checkout-http-500", 8),
        ("checkout-latency", 6),
    ],
    "smoke": [("checkout-http-500", 5)],
}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def make(*args: str) -> None:
    subprocess.run(["make", "-s", *args], cwd=ROOT, check=True, capture_output=True)


def service_of(scenario: str) -> str:
    for line in CATALOG.read_text().splitlines():
        if line.startswith(f"{scenario}="):
            return line.split("=", 1)[1].split("|")[0]
    raise SystemExit(f"unknown scenario {scenario}")


def run(scenario: str, rps: int, stable_s: int, hold_s: int, recover_s: int) -> dict[str, object]:
    make("reset-demo")
    subprocess.run(
        ["make", "-s", "load-normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env={**_env(), "RPS": str(rps)},
    )
    stable_start = now()
    time.sleep(stable_s)
    make("inject-failure", f"SCENARIO={scenario}")
    fault_start = now()  # the faulty release is fully rolled out
    time.sleep(hold_s)
    make("reset-demo")
    fault_end = now()  # the healthy release is fully rolled out again
    time.sleep(recover_s)
    return {
        "scenario": scenario,
        "service": service_of(scenario),
        "rps": rps,
        "stable_start": stable_start,
        "fault_start": fault_start,
        "fault_end": fault_end,
        "recovered_at": now(),
    }


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="default", choices=sorted(PLANS))
    parser.add_argument("--stable", type=int, default=300, help="seconds of normal traffic first")
    parser.add_argument("--hold", type=int, default=240, help="seconds the fault stays")
    parser.add_argument("--recover", type=int, default=180, help="seconds recorded after rollback")
    args = parser.parse_args()
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    for scenario, rps in PLANS[args.plan]:
        record = run(scenario, rps, args.stable, args.hold, args.recover)
        with RUNS.open("a") as f:
            f.write(json.dumps(record) + "\n")
        print(json.dumps(record), flush=True)
    make("load-normal")  # back to the default rate


if __name__ == "__main__":
    main()
