"""Phase 6 validation: one sustained failure, exactly one incident.

Needs the kind stack with load running (`make deploy-local load-normal`), the
demo catalog seeded (`make seed`), and the API and detection worker running
(`make dev`). Then:

    make test-detection

1. Under normal load, no detector incident opens for a minute.
2. Ship the faulty checkout release; exactly one detector incident opens,
   on checkout, within 120 s. The detection delay is recorded.
3. Restore the healthy release; the incident records the recovery.
4. Resolve the incident so the next run starts clean.
"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import httpx

ROOT = Path(__file__).resolve().parents[2]
API = f"http://127.0.0.1:{os.environ.get('API_PORT', '8000')}/api/v1"
DETECTION_BUDGET_SECONDS = 120
RESULTS = ROOT / "test-results" / "detection"
ACTIVE = [
    "DETECTED",
    "INVESTIGATING",
    "AWAITING_APPROVAL",
    "REMEDIATING",
    "VERIFYING",
    "MONITORING",
    "REJECTED",
]


def fail(message: str) -> NoReturn:
    sys.exit(f"FAIL: {message}")


def token() -> str:
    script = ROOT / "scripts" / "dev-token.sh"
    return subprocess.run(  # noqa: S603 - repository script
        [str(script), "commander"], check=True, capture_output=True, text=True
    ).stdout.strip()


def make(*targets: str) -> None:
    subprocess.run(["make", "--no-print-directory", *targets], cwd=ROOT, check=True)  # noqa: S603, S607


def detector_incidents(client: httpx.Client, since: datetime) -> list[dict[str, Any]]:
    response = client.get(
        "/incidents",
        params={"source": "detector", "since": since.isoformat(), "limit": 200},
    )
    response.raise_for_status()
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def main() -> None:
    client = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {token()}"}, timeout=10)
    services = {s["slug"]: s for s in client.get("/services").raise_for_status().json()["items"]}
    if "checkout" not in services:
        fail("the demo catalog is not seeded; run make seed")
    checkout_id = services["checkout"]["id"]
    open_ones = client.get(
        "/incidents",
        params={"source": "detector", "service_id": checkout_id, "status": ACTIVE},
    ).json()["items"]
    if open_ones:
        fail(f"checkout already has an open detector incident: {open_ones[0]['id']}")

    start = datetime.now(UTC)
    print("observing normal load for 60 s", flush=True)
    time.sleep(60)
    if found := detector_incidents(client, start):
        fail(f"{len(found)} detector incident(s) opened under normal load")
    print("PASS no incident under normal load", flush=True)

    injected = datetime.now(UTC)
    subprocess.run([str(ROOT / "scripts" / "inject-failure.sh"), "checkout-http-500"], check=True)  # noqa: S603
    incident = None
    deadline = time.monotonic() + DETECTION_BUDGET_SECONDS + 30
    while time.monotonic() < deadline and incident is None:
        time.sleep(3)
        found = detector_incidents(client, injected)
        incident = next((i for i in found if i["service_id"] == checkout_id), None)
    if incident is None:
        fail("no detector incident for checkout")
    delay = (datetime.fromisoformat(incident["started_at"]) - injected).total_seconds()
    time.sleep(30)  # let callers' readings settle before counting
    opened = detector_incidents(client, injected)
    if len(opened) != 1:
        fail(f"expected exactly one detector incident, got {[i['title'] for i in opened]}")
    if delay > DETECTION_BUDGET_SECONDS:
        fail(f"detected after {delay:.0f} s, budget {DETECTION_BUDGET_SECONDS} s")
    print(f"PASS one incident ({incident['severity']}) on checkout after {delay:.0f} s", flush=True)

    make("reset-demo")
    recovered = None
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline and recovered is None:
        time.sleep(5)
        events = client.get(f"/incidents/{incident['id']}/events").json()["items"]
        recovered = next(
            (e for e in events if e["event_type"] == "incident.signal_recovered"), None
        )
    if recovered is None:
        fail("the incident never recorded recovery")
    recovery = (datetime.fromisoformat(recovered["created_at"]) - injected).total_seconds()
    print(f"PASS recovery recorded {recovery:.0f} s after injection", flush=True)

    current = client.get(f"/incidents/{incident['id']}").json()
    for step in ("investigate", "monitor", "resolve"):
        if step == "monitor":
            response = client.patch(
                f"/incidents/{incident['id']}",
                json={"version": current["version"], "status": "MONITORING"},
            )
        else:
            response = client.post(
                f"/incidents/{incident['id']}/{step}", json={"version": current["version"]}
            )
        current = response.raise_for_status().json()
    print("resolved the incident", flush=True)

    RESULTS.mkdir(parents=True, exist_ok=True)
    summary = {
        "injected_at": injected.isoformat(),
        "scenario": "checkout-http-500",
        "incident_id": incident["id"],
        "severity": incident["severity"],
        "detection_delay_seconds": round(delay, 1),
        "recovery_recorded_after_seconds": round(recovery, 1),
        "detector_incidents_opened": len(opened),
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
