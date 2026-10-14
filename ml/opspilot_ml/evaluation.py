"""Detector metrics on labelled windows: row-level and per incident."""

import time
from typing import Any, Protocol

import numpy as np
import pandas as pd

from opspilot_ml.features import STEP

# After a fault ends, the rollback is still rolling out; alerts then are not false.
RECOVERY_GRACE = pd.Timedelta(minutes=2)


class Detector(Protocol):
    name: str

    def predict(self, frame: pd.DataFrame) -> pd.Series: ...


def chronological_split(frame: pd.DataFrame, test_runs: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Whole runs in time order: the last `test_runs` runs are the test set."""
    order = frame.groupby("run")["time"].min().sort_values().index.tolist()
    test = set(order[-test_runs:])
    is_test = frame["run"].isin(test)
    train, held_out = frame[~is_test], frame[is_test]
    if not train.empty and not held_out.empty and train["time"].max() >= held_out["time"].min():
        raise ValueError("training data overlaps the test period")
    return train, held_out


def _episodes(alerts: pd.Series, frame: pd.DataFrame) -> int:
    """Number of alert episodes (rising edges) per service."""
    total = 0
    for _, group in frame.sort_values("time").groupby("service", sort=False):
        a = alerts.loc[group.index].astype(int)
        total += int(((a == 1) & (a.shift(1, fill_value=0) == 0)).sum())
    return total


def evaluate(detector: Detector, frame: pd.DataFrame, runs: list[Any]) -> dict[str, Any]:
    """Precision/recall/F1 on rows, false alerts per hour, detection delay, misses, latency."""
    started = time.perf_counter()
    alerts = detector.predict(frame)
    per_row_ms = (time.perf_counter() - started) * 1000 / max(len(frame), 1)

    truth = frame["anomaly"] == 1
    grace = pd.Series(False, index=frame.index)
    delays: list[float] = []
    missed = 0
    for run_id in sorted(frame["run"].unique()):
        run = runs[int(run_id)]
        rows = frame[(frame["run"] == run_id) & (frame["service"] == run.service)]
        tail = (rows["time"] >= run.fault_end) & (rows["time"] < run.fault_end + RECOVERY_GRACE)
        grace.loc[rows.index[tail]] = True
        hits = rows[
            alerts.loc[rows.index]
            & (rows["time"] >= run.fault_start)
            & (rows["time"] < run.fault_end + RECOVERY_GRACE)
        ]
        if hits.empty:
            missed += 1
        else:
            delays.append((hits["time"].min() - run.fault_start).total_seconds())

    # Callers of a failing service and the recovery tail are neither hits nor false alerts.
    if "fault_active" in frame:
        grace |= (frame["fault_active"] == 1) & ~truth
    scored = ~grace
    tp = int((alerts & truth & scored).sum())
    fp = int((alerts & ~truth & scored).sum())
    fn = int((~alerts & truth & scored).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    false_alerts = _episodes(alerts & ~truth & scored, frame)
    hours = frame["time"].nunique() * STEP.total_seconds() / 3600
    return {
        "detector": detector.name,
        "rows": len(frame),
        "incidents": len(frame["run"].unique()),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "false_alerts_per_hour": round(false_alerts / hours, 2) if hours else 0.0,
        "median_detection_delay_s": round(float(np.median(delays)), 1) if delays else None,
        "p95_detection_delay_s": round(float(np.percentile(delays, 95)), 1) if delays else None,
        "missed_incidents": missed,
        "inference_ms_per_window": round(per_row_ms, 3),
    }
