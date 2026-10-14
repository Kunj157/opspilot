import json

import numpy as np
import pandas as pd
import pytest

from opspilot_ml.features import FEATURES, FILL, Run, clean, label
from tests.conftest import synthetic_run


def test_runs_parse_from_the_label_file() -> None:
    line = json.dumps(
        {
            "scenario": "payment-timeout",
            "service": "payment",
            "rps": 5,
            "stable_start": "2026-10-14T02:00:00+00:00",
            "fault_start": "2026-10-14T02:05:00+00:00",
            "fault_end": "2026-10-14T02:09:00+00:00",
            "recovered_at": "2026-10-14T02:12:00+00:00",
        }
    )

    run = Run.parse(line)

    assert run.service == "payment"
    assert (run.fault_end - run.fault_start).total_seconds() == 240


def test_missing_values_get_their_documented_meaning() -> None:
    frame = pd.DataFrame(
        [
            {
                "time": pd.Timestamp("2026-10-14T02:00:00Z"),
                "service": "checkout",
                **{name: np.nan for name in FEATURES},
            }
        ]
    )
    frame.loc[0, "p95_seconds"] = np.inf

    cleaned = clean(frame)

    for name in FEATURES:
        assert cleaned.loc[0, name] == FILL[name]


def test_a_frame_without_the_schema_is_rejected() -> None:
    with pytest.raises(ValueError, match="lacks"):
        clean(pd.DataFrame({"time": [], "service": [], "request_rate": []}))


def test_rates_are_clipped_to_valid_ranges() -> None:
    frame, _ = synthetic_run(0)
    frame.loc[0, "error_rate"] = 3.0
    frame.loc[1, "availability"] = -1.0

    cleaned = clean(frame)

    assert cleaned["error_rate"].max() <= 1.0
    assert cleaned["availability"].min() >= 0.0


def test_only_the_faulty_service_is_labelled_while_the_fault_is_live() -> None:
    frame, run = synthetic_run(0, service="payment")

    labelled = label(frame.drop(columns=["anomaly"]), [run])

    anomalous = labelled[labelled["anomaly"] == 1]
    assert set(anomalous["service"]) == {"payment"}
    assert anomalous["time"].min() >= run.fault_start
    assert anomalous["time"].max() < run.fault_end
    assert len(anomalous) == 16  # 4 minutes of 15 s windows
