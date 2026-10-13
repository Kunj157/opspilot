"""Command-center incident metrics: response times and severity breakdowns."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Date, SQLColumnExpression, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import scoped
from opspilot_api.db.models import Incident, IncidentStatus, Severity
from opspilot_api.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["incidents"])


class SeverityCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class DailySeverity(SeverityCounts):
    date: date


class IncidentMetrics(BaseModel):
    window_days: int
    # Mean time to acknowledge, over incidents started in the window.
    mtta_seconds: float | None
    # Mean time to resolve, over incidents resolved in the window.
    mttr_seconds: float | None
    acknowledged: int
    resolved: int
    active_by_severity: SeverityCounts
    daily: list[DailySeverity]


def _seconds(end: SQLColumnExpression[Any], start: SQLColumnExpression[Any]) -> ColumnElement[Any]:
    """Average of `end - start` in seconds; rows where `end` is NULL are ignored."""
    return func.avg(func.extract("epoch", end - start))


@router.get("/incident-metrics", response_model=IncidentMetrics)
async def incident_metrics(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> IncidentMetrics:
    today = datetime.now(UTC).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=UTC)

    mtta, acknowledged = (
        await session.execute(
            scoped(
                select(
                    _seconds(Incident.acknowledged_at, Incident.started_at),
                    func.count(Incident.acknowledged_at),
                ),
                Incident,
                principal,
            ).where(Incident.started_at >= since, Incident.acknowledged_at.is_not(None))
        )
    ).one()
    mttr, resolved = (
        await session.execute(
            scoped(
                select(_seconds(Incident.resolved_at, Incident.started_at), func.count()),
                Incident,
                principal,
            ).where(Incident.resolved_at >= since)
        )
    ).one()

    active = await session.execute(
        scoped(select(Incident.severity, func.count()), Incident, principal)
        .where(Incident.status != IncidentStatus.RESOLVED)
        .group_by(Incident.severity)
    )
    day = cast(func.timezone("UTC", Incident.started_at), Date)
    started = await session.execute(
        scoped(select(day, Incident.severity, func.count()), Incident, principal)
        .where(Incident.started_at >= since)
        .group_by(day, Incident.severity)
    )

    daily = {
        first_day + timedelta(days=i): DailySeverity(date=first_day + timedelta(days=i))
        for i in range(days)
    }
    for when, severity, count in started:
        if when in daily:
            setattr(daily[when], Severity(severity).value, count)

    return IncidentMetrics(
        window_days=days,
        mtta_seconds=float(mtta) if mtta is not None else None,
        mttr_seconds=float(mttr) if mttr is not None else None,
        acknowledged=acknowledged,
        resolved=resolved,
        active_by_severity=SeverityCounts(**{Severity(s).value: n for s, n in active}),
        daily=list(daily.values()),
    )
