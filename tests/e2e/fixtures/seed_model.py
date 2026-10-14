"""Register a model version with evaluation metrics, as `python -m opspilot_api.ml register` would.

    uv run --directory apps/api python ../../tests/e2e/fixtures/seed_model.py

Browser tests use it to render the model page without training. Needs DATABASE_URL.
"""

import json
import os

import psycopg

METRICS = {
    "model": {
        "precision": 0.91,
        "recall": 0.84,
        "f1": 0.87,
        "false_alerts_per_hour": 0.4,
        "median_detection_delay_s": 45,
        "p95_detection_delay_s": 60,
        "missed_incidents": 0,
        "inference_ms_per_window": 0.8,
    },
    "baseline": {
        "precision": 0.95,
        "recall": 0.62,
        "f1": 0.75,
        "false_alerts_per_hour": 0.2,
        "median_detection_delay_s": 75,
        "p95_detection_delay_s": 90,
        "missed_incidents": 1,
        "inference_ms_per_window": 0.3,
    },
    "promotable": True,
    "reason": "beats or complements the baseline",
    "test": {"runs": [5, 6], "scenarios": ["checkout-http-500", "checkout-latency"]},
}


def main() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        conn.execute("update model_versions set status = 'retired' where status = 'shadow'")
        conn.execute(
            """
            insert into model_versions
                (name, version, artifact_uri, feature_schema, metrics, status, promoted_at)
            select 'isolation-forest', coalesce(max(version), 0) + 1,
                   'models/isolation-forest-v1.joblib', %s, %s, 'shadow', now()
            from model_versions where name = 'isolation-forest'
            """,
            (
                json.dumps({"version": "v1", "features": ["request_rate", "error_rate"]}),
                json.dumps(METRICS),
            ),
        )


if __name__ == "__main__":
    main()
