import time

import joblib
import numpy as np
import pandas as pd
import pytest

from opspilot_ml.detectors import IsolationForestDetector, RollingZScore, deviations
from opspilot_ml.evaluation import chronological_split, evaluate


def test_deviations_never_use_future_rows(dataset: tuple[pd.DataFrame, list]) -> None:
    frame, _ = dataset
    cut = frame["time"].sort_values().iloc[len(frame) // 2]
    before = deviations(frame)
    future = frame.copy()
    future.loc[future["time"] > cut, ["error_rate", "p95_seconds"]] = 99.0

    after = deviations(future)

    past = frame["time"] <= cut
    pd.testing.assert_frame_equal(before[past], after[past])


def test_the_split_keeps_whole_runs_in_time_order(dataset: tuple[pd.DataFrame, list]) -> None:
    frame, _ = dataset

    train, test = chronological_split(frame, test_runs=2)

    assert set(test["run"]) == {3, 4}
    assert train["time"].max() < test["time"].min()


@pytest.mark.parametrize(
    ("detector", "min_recall"), [(RollingZScore(), 0.8), (IsolationForestDetector(), 0.5)]
)
def test_both_detectors_catch_an_error_spike(
    detector, min_recall: float, dataset: tuple[pd.DataFrame, list]
) -> None:
    frame, runs = dataset
    train, test = chronological_split(frame, test_runs=2)

    detector.fit(train)
    report = evaluate(detector, test, runs)

    assert report["missed_incidents"] == 0
    assert report["recall"] > min_recall
    assert report["precision"] > 0.8
    assert report["median_detection_delay_s"] <= 60
    assert report["false_alerts_per_hour"] < 2


def test_training_is_deterministic(dataset: tuple[pd.DataFrame, list]) -> None:
    frame, _ = dataset
    first = IsolationForestDetector().fit(frame).score(frame)
    second = IsolationForestDetector().fit(frame).score(frame)

    np.testing.assert_allclose(first, second, rtol=1e-9)


def test_the_artifact_round_trips(dataset: tuple[pd.DataFrame, list], tmp_path) -> None:
    frame, _ = dataset
    detector = IsolationForestDetector().fit(frame)
    path = tmp_path / "model.joblib"
    joblib.dump(detector, path)

    loaded = joblib.load(path)

    np.testing.assert_allclose(loaded.score(frame), detector.score(frame))
    assert loaded.describe()["schema_version"] == "v1"


def test_inference_is_fast(dataset: tuple[pd.DataFrame, list]) -> None:
    frame, _ = dataset
    detector = IsolationForestDetector().fit(frame)
    window = frame[frame["time"] >= frame["time"].max() - pd.Timedelta(minutes=10)]

    started = time.perf_counter()
    detector.predict(window)

    assert time.perf_counter() - started < 0.5
