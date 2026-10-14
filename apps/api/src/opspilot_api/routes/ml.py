"""The ML detector: model versions, promotion and rollback, scoring, and shadow results."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from opspilot_ml.features import FEATURES, clean
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.audit.service import record
from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.db.models import AnomalyDetection, Incident, ModelVersion, Service
from opspilot_api.db.session import get_session
from opspilot_api.ml.registry import ModelUnavailable, load_detector, promote, shadow_model

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: int
    status: str
    feature_schema: dict[str, Any]
    metrics: dict[str, Any]
    mlflow_run_id: str | None
    created_at: datetime
    promoted_at: datetime | None


class ModelList(BaseModel):
    items: list[ModelOut]


@router.get("/models", response_model=ModelList)
async def list_models(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ModelList:
    rows = await session.scalars(
        select(ModelVersion).order_by(ModelVersion.name, ModelVersion.version.desc())
    )
    return ModelList(items=[ModelOut.model_validate(r) for r in rows])


@router.post("/models/{model_id}/promote", response_model=ModelOut)
async def promote_model(
    model_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_MODELS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ModelOut:
    """Run this version in shadow mode; promoting an older version is the rollback."""
    model = await session.get(ModelVersion, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    try:
        load_detector(model.artifact_uri, model.feature_schema["version"])
    except ModelUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    previous = await shadow_model(session)
    await promote(session, model)
    await record(
        session,
        principal=principal,
        action="model.promoted",
        resource_type="model_version",
        resource_id=str(model.id),
        metadata={
            "name": model.name,
            "version": model.version,
            "replaces": f"{previous.name}:{previous.version}" if previous else None,
        },
    )
    await session.commit()
    return ModelOut.model_validate(model)


class Window(BaseModel):
    """One 15 s feature window of one service (feature schema v1)."""

    model_config = ConfigDict(extra="forbid")

    time: datetime
    service: str = Field(min_length=1, max_length=63)
    request_rate: float | None = None
    error_rate: float | None = None
    p50_seconds: float | None = None
    p95_seconds: float | None = None
    p99_seconds: float | None = None
    restarts_5m: float | None = None
    availability: float | None = None


class ScoreIn(BaseModel):
    windows: list[Window] = Field(min_length=1, max_length=2000)


class Score(BaseModel):
    time: datetime
    service: str
    score: float
    alert: bool


class ScoreOut(BaseModel):
    model: str
    threshold: float
    scores: list[Score]


@router.post("/score", response_model=ScoreOut)
async def score_windows(
    body: ScoreIn,
    principal: Annotated[Principal, Depends(require(Permission.START_INVESTIGATION))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScoreOut:
    """Score posted windows with the shadow model (history first, newest last)."""
    model = await shadow_model(session)
    if model is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No model is in shadow mode")
    try:
        detector = load_detector(model.artifact_uri, model.feature_schema["version"])
    except ModelUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    frame = clean(pd.DataFrame([w.model_dump() for w in body.windows]))
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    scores, alerts = detector.score(frame), detector.predict(frame)
    return ScoreOut(
        model=f"{model.name}:{model.version}",
        threshold=float(detector.threshold),
        scores=[
            Score(
                time=frame.loc[i, "time"].to_pydatetime(),
                service=str(frame.loc[i, "service"]),
                score=float(scores.loc[i]),
                alert=bool(alerts.loc[i]),
            )
            for i in frame.index
        ],
    )


class ServiceComparison(BaseModel):
    service_id: uuid.UUID
    service: str
    shadow_windows: int
    shadow_alerts: int
    rule_triggers: int
    incidents: int


class ShadowSummary(BaseModel):
    since: datetime
    model: str | None
    services: list[ServiceComparison]
    features: list[str] = FEATURES


@router.get("/shadow", response_model=ShadowSummary)
async def shadow_summary(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> ShadowSummary:
    """Per service: shadow predictions and alerts next to the rule's triggers and incidents."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    model = await shadow_model(session)
    detections = (
        select(
            AnomalyDetection.service_id,
            func.count().filter(AnomalyDetection.outcome.like("shadow%")).label("windows"),
            func.count().filter(AnomalyDetection.outcome == "shadow_alert").label("alerts"),
            func.sum(case((AnomalyDetection.outcome == "triggered", 1), else_=0)).label("rule"),
        )
        .where(
            AnomalyDetection.organization_id == principal.organization_id,
            AnomalyDetection.created_at >= since,
        )
        .group_by(AnomalyDetection.service_id)
        .subquery()
    )
    incidents = (
        select(Incident.service_id, func.count().label("incidents"))
        .where(Incident.organization_id == principal.organization_id, Incident.started_at >= since)
        .group_by(Incident.service_id)
        .subquery()
    )
    rows = await session.execute(
        select(
            Service.id,
            Service.name,
            func.coalesce(detections.c.windows, 0),
            func.coalesce(detections.c.alerts, 0),
            func.coalesce(detections.c.rule, 0),
            func.coalesce(incidents.c.incidents, 0),
        )
        .outerjoin(detections, detections.c.service_id == Service.id)
        .outerjoin(incidents, incidents.c.service_id == Service.id)
        .where(Service.organization_id == principal.organization_id)
        .order_by(Service.name)
    )
    return ShadowSummary(
        since=since,
        model=f"{model.name}:{model.version}" if model else None,
        services=[
            ServiceComparison(
                service_id=sid,
                service=name,
                shadow_windows=int(w),
                shadow_alerts=int(a),
                rule_triggers=int(r),
                incidents=int(i),
            )
            for sid, name, w, a, r, i in rows
        ],
    )
