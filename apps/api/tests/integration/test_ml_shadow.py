"""The ML detector: registration, promotion and rollback, scoring, and shadow predictions."""

import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa
from opspilot_ml.detectors import IsolationForestDetector
from opspilot_ml.features import FEATURES
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from opspilot_api.db.models import AnomalyDetection, AuditLog, ModelVersion, Organization, Service
from opspilot_api.ml.registry import promote, register
from opspilot_api.ml.shadow import ShadowScorer
from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration
NOW = datetime.now(UTC).replace(microsecond=0)


def windows(minutes: int = 12, failing: str | None = None, seed: int = 0) -> pd.DataFrame:
    """Two services every 15 s; `failing` has 40% errors in the last 2 minutes."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(minutes * 4):
        t = NOW - timedelta(seconds=15 * (minutes * 4 - 1 - i))
        for service in ("checkout", "payment"):
            broken = service == failing and t > NOW - timedelta(minutes=2)
            rows.append(
                {
                    "time": pd.Timestamp(t),
                    "service": service,
                    "request_rate": 5 + rng.normal(0, 0.2),
                    "error_rate": (0.4 if broken else 0.0) + abs(rng.normal(0, 0.002)),
                    "p50_seconds": 0.02,
                    "p95_seconds": 0.05 + rng.normal(0, 0.002),
                    "p99_seconds": 0.08,
                    "restarts_5m": 0.0,
                    "availability": 1.0,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    """A trained artifact and its evaluation report, laid out like ml/."""
    root = tmp_path_factory.mktemp("ml")
    (root / "models").mkdir()
    frame = pd.concat([windows(seed=s) for s in range(4)], ignore_index=True)
    frame["anomaly"] = 0
    detector = IsolationForestDetector().fit(frame)
    joblib.dump(detector, root / "models" / "isolation-forest-v1.joblib")
    return (
        {
            "isolation-forest": {"f1": 0.9, "false_alerts_per_hour": 0.4},
            "rolling-zscore": {"f1": 0.8, "false_alerts_per_hour": 0.9},
            "test": {"runs": [5, 6]},
            "promotion": {
                "promotable": True,
                "reason": "beats or complements the baseline",
                "artifact": "models/isolation-forest-v1.joblib",
                "mlflow_run_id": "abc123",
                "detector": detector.describe(),
            },
        },
        root,
    )


@pytest.fixture
async def sessions(migrated_database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory
) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(migrated_database_url, factory) as c:
        yield c


async def registered(
    sessions: async_sessionmaker[AsyncSession],
    report: tuple[dict[str, Any], Path],
    *,
    shadow: bool = True,
) -> ModelVersion:
    async with sessions() as session:
        model = await register(session, *report)
        if shadow:
            await promote(session, model)
        await session.commit()
        return model


async def test_registration_records_schema_metrics_and_artifact(
    sessions: async_sessionmaker[AsyncSession], report: tuple[dict[str, Any], Path]
) -> None:
    first = await registered(sessions, report, shadow=False)
    second = await registered(sessions, report, shadow=False)

    assert second.version == first.version + 1
    assert first.status == "candidate"
    assert first.feature_schema["version"] == "v1"
    assert first.feature_schema["features"] == FEATURES
    assert first.metrics["model"]["f1"] == 0.9
    assert first.artifact_uri.endswith("models/isolation-forest-v1.joblib")
    assert first.mlflow_run_id == "abc123"


async def test_an_admin_promotes_and_rolls_back(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    factory: TokenFactory,
    report: tuple[dict[str, Any], Path],
) -> None:
    old = await registered(sessions, report)
    new = await registered(sessions, report, shadow=False)
    admin = Caller(factory, new_org(), "administrator")

    promoted = await client.post(f"/api/v1/ml/models/{new.id}/promote", headers=admin.headers)
    rolled_back = await client.post(f"/api/v1/ml/models/{old.id}/promote", headers=admin.headers)
    listed = await client.get("/api/v1/ml/models", headers=admin.headers)

    assert promoted.status_code == 200, promoted.text
    assert rolled_back.json()["status"] == "shadow"
    statuses = {m["id"]: m["status"] for m in listed.json()["items"]}
    assert statuses[str(old.id)] == "shadow"
    assert statuses[str(new.id)] == "retired"
    assert list(statuses.values()).count("shadow") == 1
    async with sessions() as session:
        audit = list(
            await session.scalars(
                sa.select(AuditLog.metadata_json).where(AuditLog.action == "model.promoted")
            )
        )
    assert any(a.get("replaces") == f"{new.name}:{new.version}" for a in audit)


async def test_a_retried_promotion_with_the_same_key_is_replayed(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    factory: TokenFactory,
    report: tuple[dict[str, Any], Path],
) -> None:
    model = await registered(sessions, report, shadow=False)
    admin = Caller(factory, new_org(), "administrator")
    headers = {**admin.headers, "Idempotency-Key": "promote-once"}
    path = f"/api/v1/ml/models/{model.id}/promote"

    first = await client.post(path, headers=headers)
    second = await client.post(path, headers=headers)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert second.headers["Idempotency-Replayed"] == "true"
    async with sessions() as session:
        promotions = await session.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "model.promoted", AuditLog.resource_id == str(model.id))
        )
    assert promotions == 1


async def test_only_administrators_promote(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    factory: TokenFactory,
    report: tuple[dict[str, Any], Path],
) -> None:
    model = await registered(sessions, report, shadow=False)

    for role in ("viewer", "operator", "incident-commander"):
        response = await client.post(
            f"/api/v1/ml/models/{model.id}/promote",
            headers=Caller(factory, new_org(), role).headers,
        )
        assert response.status_code == 403, role


async def test_a_model_whose_artifact_is_gone_cannot_be_promoted(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    async with sessions() as session:
        broken = ModelVersion(
            name="isolation-forest",
            version=900 + int(time.time()) % 99,
            artifact_uri="/nonexistent/model.joblib",
            feature_schema={"version": "v1"},
        )
        session.add(broken)
        await session.commit()

    response = await client.post(
        f"/api/v1/ml/models/{broken.id}/promote",
        headers=Caller(factory, new_org(), "administrator").headers,
    )

    assert response.status_code == 409


async def test_operators_score_windows_with_the_shadow_model(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    factory: TokenFactory,
    report: tuple[dict[str, Any], Path],
) -> None:
    await registered(sessions, report)
    frame = windows(failing="checkout")
    body = {
        "windows": [
            {
                **{k: row[k] for k in FEATURES},
                "service": row["service"],
                "time": row["time"].isoformat(),
            }
            for row in frame.to_dict("records")
        ]
    }

    response = await client.post(
        "/api/v1/ml/score", json=body, headers=Caller(factory, new_org(), "operator").headers
    )
    viewer = await client.post(
        "/api/v1/ml/score", json=body, headers=Caller(factory, new_org(), "viewer").headers
    )
    bad = await client.post(
        "/api/v1/ml/score",
        json={"windows": [{**body["windows"][0], "cpu": 0.5}]},
        headers=Caller(factory, new_org(), "operator").headers,
    )

    assert response.status_code == 200, response.text
    scores = response.json()["scores"]
    last = {s["service"]: s for s in scores[-2:]}
    assert last["checkout"]["alert"] is True
    assert last["payment"]["alert"] is False
    assert viewer.status_code == 403
    assert bad.status_code == 422


async def test_the_worker_stores_shadow_predictions_without_acting(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    factory: TokenFactory,
    report: tuple[dict[str, Any], Path],
) -> None:
    model = await registered(sessions, report)
    org_slug = new_org()
    async with sessions() as session:
        org = Organization(name="Acme", slug=org_slug)
        session.add(org)
        await session.flush()
        for slug in ("checkout", "payment"):
            session.add(
                Service(
                    organization_id=org.id,
                    name=slug.capitalize(),
                    slug=slug,
                    namespace="demo",
                    deployment_name=slug,
                )
            )
        await session.commit()
    scorer = ShadowScorer(
        sessions, lambda start, end: windows(failing="checkout"), frozenset({"demo"})
    )

    started = time.perf_counter()
    stored = await scorer.cycle(NOW)
    elapsed = time.perf_counter() - started

    assert stored >= 2
    assert elapsed < 2.0
    async with sessions() as session:
        rows = list(
            await session.scalars(
                sa.select(AnomalyDetection).where(AnomalyDetection.organization_id == org.id)
            )
        )
    assert len({r.service_id for r in rows}) == 2
    assert {r.outcome for r in rows} == {"shadow_alert", "shadow_normal"}
    assert all(r.incident_id is None for r in rows)
    assert all(r.model_version == f"{model.name}:{model.version}" for r in rows)
    assert all(set(r.features) == set(FEATURES) for r in rows)

    viewer = Caller(factory, org_slug, "viewer")
    summary = await client.get("/api/v1/ml/shadow", headers=viewer.headers)
    counts = {s["service"]: s for s in summary.json()["services"]}
    assert counts["Checkout"]["shadow_alerts"] == 1
    assert counts["Payment"]["shadow_alerts"] == 0
    assert counts["Payment"]["shadow_windows"] == 1


async def test_no_shadow_model_means_no_predictions(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        await session.execute(
            sa.update(ModelVersion).where(ModelVersion.status == "shadow").values(status="retired")
        )
        await session.commit()
    scorer = ShadowScorer(sessions, lambda start, end: windows(), frozenset({"demo"}))

    assert await scorer.cycle(NOW) == 0


def test_the_report_format_matches_training(report: tuple[dict[str, Any], Path]) -> None:
    content, root = report
    assert json.loads(json.dumps(content))["promotion"]["artifact"].startswith("models/")
    assert (root / content["promotion"]["artifact"]).is_file()
