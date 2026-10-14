"""Read the labelled runs back from Prometheus into feature windows.

    uv run --directory ml python pipelines/build_dataset.py [--prometheus http://localhost:39090]

Writes datasets/windows-<schema>.csv: one row per service per 15 s window,
with `anomaly` and `run` labels.
"""

import argparse
from pathlib import Path

from opspilot_ml.features import SCHEMA_VERSION, build, load_runs

HERE = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prometheus", default="http://localhost:39090")
    parser.add_argument("--runs", type=Path, default=HERE / "datasets" / "runs.jsonl")
    args = parser.parse_args()
    runs = load_runs(args.runs)
    frame = build(args.prometheus, runs)
    out = HERE / "datasets" / f"windows-{SCHEMA_VERSION}.csv"
    frame.to_csv(out, index=False)
    print(
        f"{len(frame)} windows from {len(runs)} runs, "
        f"{int(frame['anomaly'].sum())} anomalous → {out}"
    )


if __name__ == "__main__":
    main()
