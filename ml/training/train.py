"""Train and evaluate the baseline and the Isolation Forest, track them in MLflow.

    uv run --directory ml python training/train.py [--test-runs 2]

The last runs in time are held out whole for testing. Writes the evaluation
report to evaluation/, the promoted artifact to models/, and registers the
model in the local MLflow registry (sqlite:///mlflow.db).
"""

import argparse
import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
import sklearn

from opspilot_ml.detectors import IsolationForestDetector, RollingZScore
from opspilot_ml.evaluation import chronological_split, evaluate
from opspilot_ml.features import FEATURES, SCHEMA_VERSION, load_runs

HERE = Path(__file__).resolve().parents[1]
MODEL_NAME = "opspilot-anomaly"
# Promotion rule (plan §18.5): beat or complement the baseline, keep false
# alerts low, and score a window fast enough for the 15 s detection cycle.
MAX_FALSE_ALERTS_PER_HOUR = 1.0
MAX_INFERENCE_MS = 5.0


def promotable(model: dict[str, float], baseline: dict[str, float]) -> tuple[bool, str]:
    if model["false_alerts_per_hour"] > MAX_FALSE_ALERTS_PER_HOUR:
        return False, f"{model['false_alerts_per_hour']} false alerts per hour"
    if model["inference_ms_per_window"] > MAX_INFERENCE_MS:
        return False, f"{model['inference_ms_per_window']} ms per window"
    better = model["f1"] > baseline["f1"]
    faster = (model["median_detection_delay_s"] or 1e9) < (
        baseline["median_detection_delay_s"] or 1e9
    )
    catches_more = model["missed_incidents"] < baseline["missed_incidents"]
    if better or faster or catches_more:
        return True, "beats or complements the baseline"
    return False, "no better than the baseline"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-runs", type=int, default=2)
    args = parser.parse_args()
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

    runs = load_runs(HERE / "datasets" / "runs.jsonl")
    frame = pd.read_csv(HERE / "datasets" / f"windows-{SCHEMA_VERSION}.csv", parse_dates=["time"])
    train, test = chronological_split(frame, args.test_runs)

    mlflow.set_tracking_uri(f"sqlite:///{HERE / 'mlflow.db'}")
    mlflow.set_experiment("anomaly-detection")
    reports = {}
    for detector in (RollingZScore(), IsolationForestDetector()):
        with mlflow.start_run(run_name=detector.name) as run:
            detector.fit(train)
            report = evaluate(detector, test, runs)
            reports[detector.name] = report
            mlflow.log_params(
                {
                    "schema_version": SCHEMA_VERSION,
                    "features": ",".join(FEATURES),
                    "train_runs": int(train["run"].nunique()),
                    "test_runs": int(test["run"].nunique()),
                    "persistence": detector.persistence,
                }
            )
            mlflow.log_metrics(
                {k: float(v) for k, v in report.items() if isinstance(v, int | float)}
            )
            if isinstance(detector, IsolationForestDetector):
                ok, why = promotable(report, reports["rolling-zscore"])
                mlflow.set_tags({"promotable": str(ok), "promotion_reason": why})
                artifact = HERE / "models" / f"isolation-forest-{SCHEMA_VERSION}.joblib"
                artifact.parent.mkdir(exist_ok=True)  # gitignored, so absent in a fresh clone
                joblib.dump(detector, artifact)
                mlflow.log_dict(detector.describe(), "detector.json")
                mlflow.log_artifact(str(artifact))
                assert detector.model is not None
                info = mlflow.sklearn.log_model(
                    detector.model,
                    name="model",
                    registered_model_name=MODEL_NAME,
                    skops_trusted_types=["sklearn.tree._tree.Tree"],
                )
                reports["promotion"] = {
                    "promotable": ok,
                    "reason": why,
                    "registered_model": MODEL_NAME,
                    "registered_version": info.registered_model_version,
                    "mlflow_run_id": run.info.run_id,
                    "artifact": str(artifact.relative_to(HERE)),
                    "detector": detector.describe(),
                }

    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "schema_version": SCHEMA_VERSION,
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "train": {"runs": sorted(int(r) for r in train["run"].unique()), "windows": len(train)},
        "test": {
            "runs": sorted(int(r) for r in test["run"].unique()),
            "windows": len(test),
            "scenarios": [runs[int(r)].scenario for r in sorted(test["run"].unique())],
        },
        **reports,
    }
    out = HERE / "evaluation" / f"report-{SCHEMA_VERSION}.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
