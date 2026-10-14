"""Two detectors on the same feature windows.

Both see only the past: deviations are measured against a trailing window
that ends one row before the scored row, per service, using the median and
median absolute deviation so that a sustained fault does not become the new normal
within minutes. Both alert only with
minimum traffic and only after the score stays high for `persistence` rows.

- RollingZScore (baseline): the largest absolute z-score of any feature.
- IsolationForestDetector: an Isolation Forest trained on normal windows
  only, over the same deviations plus the raw error rate and availability.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from opspilot_ml.features import FEATURES, SCHEMA_VERSION

TRAILING = 40  # rows = 10 minutes of 15 s windows
MIN_HISTORY = 8  # rows before a service is scored at all
STD_FLOOR = {
    "request_rate": 0.2,
    "error_rate": 0.01,
    "p50_seconds": 0.005,
    "p95_seconds": 0.01,
    "p99_seconds": 0.02,
    "restarts_5m": 0.5,
    "availability": 0.05,
}


def _mad(values: np.ndarray) -> float:
    """Median absolute deviation, ignoring missing values."""
    values = values[~np.isnan(values)]
    return float(np.median(np.abs(values - np.median(values)))) if len(values) else np.nan


def deviations(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-feature robust z-scores against each service's trailing window (past rows only)."""
    out = []
    for _, group in frame.sort_values("time").groupby("service", sort=False):
        history = group[FEATURES].shift(1).rolling(TRAILING, min_periods=MIN_HISTORY)
        # Robust centre and spread: a fault shorter than half the window cannot drag them along.
        centre = history.median()
        spread = history.apply(_mad, raw=True) * 1.4826
        floor = pd.Series(STD_FLOOR)[FEATURES]
        scale = spread.fillna(0.0).clip(lower=floor, axis=1)
        z = (group[FEATURES] - centre) / scale
        z.columns = [f"z_{c}" for c in FEATURES]
        out.append(z)
    return pd.concat(out).reindex(frame.index)


def persist(raw: pd.Series, frame: pd.DataFrame, rows: int) -> pd.Series:
    """True once `raw` has held for `rows` consecutive rows of the same service."""
    held = pd.Series(False, index=frame.index)
    for _, group in frame.sort_values("time").groupby("service", sort=False):
        flags = raw.loc[group.index].astype(int)
        streak = flags.groupby((flags == 0).cumsum()).cumsum()
        held.loc[group.index] = streak >= rows
    return held


@dataclass
class RollingZScore:
    threshold: float = 6.0
    persistence: int = 2
    min_traffic: float = 0.5
    name: str = "rolling-zscore"

    def score(self, frame: pd.DataFrame) -> pd.Series:
        z = deviations(frame)
        # Only deviations that mean trouble: more errors and latency, less traffic served.
        harmful = pd.concat(
            [
                z[["z_error_rate", "z_p50_seconds", "z_p95_seconds", "z_p99_seconds"]].clip(
                    lower=0
                ),
                z[["z_restarts_5m"]].clip(lower=0),
                (-z[["z_availability"]]).clip(lower=0),
            ],
            axis=1,
        )
        return harmful.max(axis=1).fillna(0.0)

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        raw = (self.score(frame) > self.threshold) & (frame["request_rate"] >= self.min_traffic)
        return persist(raw, frame, self.persistence)

    def fit(self, frame: pd.DataFrame) -> "RollingZScore":
        return self


@dataclass
class IsolationForestDetector:
    persistence: int = 2
    min_traffic: float = 0.5
    # Score threshold: the given quantile of scores on normal training windows.
    normal_quantile: float = 0.995
    seed: int = 7
    name: str = "isolation-forest"
    schema_version: str = SCHEMA_VERSION
    model: IsolationForest | None = None
    threshold: float = 0.0
    columns: list[str] = field(default_factory=list)

    def _inputs(self, frame: pd.DataFrame) -> pd.DataFrame:
        z = deviations(frame).fillna(0.0).clip(-50, 50)
        inputs = pd.concat([z, frame[["error_rate", "availability"]]], axis=1)
        return inputs

    def fit(self, frame: pd.DataFrame) -> "IsolationForestDetector":
        inputs = self._inputs(frame)
        normal = inputs[(frame["anomaly"] == 0) & (frame["request_rate"] >= self.min_traffic)]
        self.columns = list(inputs.columns)
        self.model = IsolationForest(n_estimators=200, random_state=self.seed).fit(
            normal[self.columns].to_numpy()
        )
        scores = -self.model.score_samples(normal[self.columns].to_numpy())
        self.threshold = float(np.quantile(scores, self.normal_quantile))
        return self

    def score(self, frame: pd.DataFrame) -> pd.Series:
        if self.model is None:
            raise RuntimeError("fit the detector first")
        inputs = self._inputs(frame)[self.columns].to_numpy()
        return pd.Series(-self.model.score_samples(inputs), index=frame.index)

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        raw = (self.score(frame) > self.threshold) & (frame["request_rate"] >= self.min_traffic)
        return persist(raw, frame, self.persistence)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema_version": self.schema_version,
            "features": FEATURES,
            "inputs": self.columns,
            "threshold": self.threshold,
            "persistence": self.persistence,
            "min_traffic": self.min_traffic,
            "trailing_rows": TRAILING,
            "seed": self.seed,
        }
