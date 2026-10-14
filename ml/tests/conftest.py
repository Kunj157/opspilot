from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from opspilot_ml.features import FEATURES, STEP, Run, clean, label

T0 = datetime(2026, 10, 14, 2, 0, tzinfo=UTC)


def synthetic_run(index: int, service: str = "checkout", seed: int = 0) -> tuple[pd.DataFrame, Run]:
    """12 minutes of three services; `service` fails with 40% errors from minute 5 to 9."""
    rng = np.random.default_rng(seed + index)
    start = T0 + timedelta(minutes=20 * index)
    times = [start + i * STEP for i in range(48)]
    run = Run(
        "checkout-http-500",
        service,
        5,
        start,
        start + timedelta(minutes=5),
        start + timedelta(minutes=9),
        start + timedelta(minutes=12),
    )
    rows = []
    for name in ("checkout", "payment", "storefront"):
        for t in times:
            faulty = name == service and run.fault_start <= t < run.fault_end
            rows.append(
                {
                    "time": pd.Timestamp(t),
                    "service": name,
                    "request_rate": 5 + rng.normal(0, 0.3),
                    "error_rate": (0.4 if faulty else 0.0) + abs(rng.normal(0, 0.003)),
                    "p50_seconds": 0.02 + rng.normal(0, 0.001),
                    "p95_seconds": 0.05 + rng.normal(0, 0.003),
                    "p99_seconds": 0.08 + rng.normal(0, 0.005),
                    "restarts_5m": 0.0,
                    "availability": 1.0,
                }
            )
    frame = label(clean(pd.DataFrame(rows)), [run])
    frame["run"] = index
    return frame, run


@pytest.fixture
def dataset() -> tuple[pd.DataFrame, list[Run]]:
    frames, runs = [], []
    for i in range(5):
        frame, run = synthetic_run(i)
        frames.append(frame)
        runs.append(run)
    return pd.concat(frames, ignore_index=True), runs


__all__ = ["FEATURES", "synthetic_run"]
