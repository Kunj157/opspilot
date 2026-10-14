"""Trained detectors known to OpsPilot, and which one runs in shadow mode.

Training (ml/training/train.py) writes an evaluation report and an artifact;
`python -m opspilot_api.ml register <report>` records them here. Exactly one
version is in shadow mode at a time; promoting another one retires it, and
promoting an older version is the rollback.
"""

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.db.models import ModelVersion

SHADOW = "shadow"


class ModelUnavailable(Exception):
    """No usable shadow model (none promoted, or its artifact cannot be loaded)."""


def read_report(report_path: Path) -> tuple[dict[str, Any], Path]:
    """An evaluation report and the ML project directory its paths are relative to."""
    return json.loads(report_path.read_text()), report_path.resolve().parent.parent


async def register(session: AsyncSession, report: dict[str, Any], ml_root: Path) -> ModelVersion:
    """Record the promotable model of an evaluation report; the caller commits."""
    promotion = report["promotion"]
    detector = promotion["detector"]
    artifact = ml_root / promotion["artifact"]
    name = detector["name"]
    latest = await session.scalar(
        select(func.max(ModelVersion.version)).where(ModelVersion.name == name)
    )
    model = ModelVersion(
        name=name,
        version=(latest or 0) + 1,
        artifact_uri=str(artifact),
        feature_schema={
            "version": detector["schema_version"],
            "features": detector["features"],
            "inputs": detector["inputs"],
        },
        metrics={
            "model": report.get(name, {}),
            "baseline": report.get("rolling-zscore", {}),
            "promotable": promotion["promotable"],
            "reason": promotion["reason"],
            "test": report.get("test", {}),
        },
        status="candidate",
        mlflow_run_id=promotion.get("mlflow_run_id"),
    )
    session.add(model)
    await session.flush()
    return model


async def promote(session: AsyncSession, model: ModelVersion) -> ModelVersion:
    """Make `model` the shadow model and retire the current one; the caller commits."""
    current = await session.scalars(
        select(ModelVersion).where(ModelVersion.status == SHADOW, ModelVersion.id != model.id)
    )
    for other in current:
        other.status = "retired"
    model.status = SHADOW
    model.promoted_at = datetime.now(UTC)
    await session.flush()
    return model


async def shadow_model(session: AsyncSession) -> ModelVersion | None:
    found: ModelVersion | None = await session.scalar(
        select(ModelVersion).where(ModelVersion.status == SHADOW)
    )
    return found


@lru_cache(maxsize=4)
def load_detector(artifact_uri: str, schema_version: str) -> Any:
    """The detector object of an artifact, checked against its recorded feature schema."""
    try:
        detector = joblib.load(artifact_uri)
    except (OSError, ValueError, ImportError) as exc:
        raise ModelUnavailable(f"cannot load {artifact_uri}: {exc}") from exc
    if getattr(detector, "schema_version", None) != schema_version:
        raise ModelUnavailable(
            f"artifact schema {getattr(detector, 'schema_version', None)} != {schema_version}"
        )
    return detector
