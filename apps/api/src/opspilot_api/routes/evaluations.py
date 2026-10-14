"""Evaluation metrics: how well detection, the agents, and remediation performed.

Everything is computed on request from the operational tables (incidents,
anomaly detections, investigations, agent runs and tool calls, approvals), so
the numbers always match what the rest of the API shows. Each field's
description says how it is derived.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, Select, SQLColumnExpression, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import scoped
from opspilot_api.db.models import (
    AgentRun,
    AgentToolCall,
    AnomalyDetection,
    Approval,
    Incident,
    Investigation,
    InvestigationStatus,
)
from opspilot_api.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["evaluations"])

DEFAULT_WINDOW = timedelta(days=30)
MAX_WINDOW = timedelta(days=366)


class DetectionMetrics(BaseModel):
    incidents: int = Field(description="Detector-opened incidents started in the range")
    delay_p50_seconds: float | None = Field(
        description="Median seconds from the start of the first anomalous evaluation window "
        "linked to an incident (anomaly_detections.window_start) to the incident opening "
        "(incidents.started_at): the detection pipeline's own delay"
    )
    delay_p95_seconds: float | None = Field(description="95th percentile of the same delay")


class InvestigationMetrics(BaseModel):
    total: int = Field(description="Investigations created in the range")
    succeeded: int = Field(description="Of those, finished with status completed")
    partial: int = Field(description="Of those, stopped early (limits or model failure)")
    failed: int = Field(description="Of those, gave up after repeated attempts")


class AgentMetrics(BaseModel):
    runs: int = Field(description="Agent (model) calls started in the range")
    success_rate: float | None = Field(
        description="Share of agent runs with status succeeded; failed calls and runs that "
        "fell back to the fixed plan count against it"
    )
    tool_calls: int = Field(description="Tool calls made in the range")
    tool_error_rate: float | None = Field(
        description="Share of tool calls that returned a failed result"
    )
    input_tokens: int = Field(description="Sum of agent_runs.input_tokens")
    output_tokens: int = Field(description="Sum of agent_runs.output_tokens")
    cost_usd: float = Field(description="Sum of agent_runs.estimated_cost (USD, estimated)")


class RemediationMetrics(BaseModel):
    decisions: int = Field(description="Human approve/reject decisions recorded in the range")
    approval_rate: float | None = Field(description="Share of those decisions that approved")


class ResponseMetrics(BaseModel):
    mtta_seconds: float | None = Field(
        description="Mean acknowledged_at - started_at over incidents started in the range"
    )
    mttr_seconds: float | None = Field(
        description="Mean resolved_at - started_at over incidents started in the range "
        "that are resolved"
    )


class Evaluations(BaseModel):
    range_start: datetime
    range_end: datetime
    detection: DetectionMetrics
    investigations: InvestigationMetrics
    agents: AgentMetrics
    remediation: RemediationMetrics
    response: ResponseMetrics


def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _seconds(end: SQLColumnExpression[Any], start: SQLColumnExpression[Any]) -> ColumnElement[Any]:
    return func.extract("epoch", end - start)


async def _one(session: AsyncSession, statement: Select[*tuple[Any, ...]]) -> Any:
    return (await session.execute(statement)).one()


@router.get("/evaluations", response_model=Evaluations)
async def evaluations(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    start: Annotated[
        datetime | None, Query(alias="from", description="Range start; default 30 days ago")
    ] = None,
    end: Annotated[datetime | None, Query(alias="to", description="Range end; default now")] = None,
) -> Evaluations:
    range_end = end or datetime.now(UTC)
    range_start = start or range_end - DEFAULT_WINDOW
    if range_start.tzinfo is None or range_end.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "from and to need a timezone")
    if not range_start < range_end or range_end - range_start > MAX_WINDOW:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "from must be before to, at most 366 days apart",
        )

    def in_range(column: Any) -> list[ColumnElement[bool]]:
        return [column >= range_start, column < range_end]

    # Detection delay: one row per detector incident, its first linked window.
    first_window = (
        scoped(
            select(
                Incident.id,
                _seconds(Incident.started_at, func.min(AnomalyDetection.window_start)).label(
                    "delay"
                ),
            ).join(AnomalyDetection, AnomalyDetection.incident_id == Incident.id),
            Incident,
            principal,
        )
        .where(Incident.source == "detector", *in_range(Incident.started_at))
        .group_by(Incident.id, Incident.started_at)
        .subquery()
    )
    delay = first_window.c.delay
    detected, p50, p95 = await _one(
        session,
        select(
            func.count(),
            func.percentile_cont(0.5).within_group(delay),
            func.percentile_cont(0.95).within_group(delay),
        ).select_from(first_window),
    )

    def count_status(value: InvestigationStatus) -> ColumnElement[Any]:
        return func.count(case((Investigation.status == value, 1)))

    total, succeeded, partial, failed = await _one(
        session,
        scoped(
            select(
                func.count(),
                count_status(InvestigationStatus.COMPLETED),
                count_status(InvestigationStatus.PARTIAL),
                count_status(InvestigationStatus.FAILED),
            ),
            Investigation,
            principal,
        ).where(*in_range(Investigation.created_at)),
    )

    runs, ok_runs, input_tokens, output_tokens, cost = await _one(
        session,
        scoped(
            select(
                func.count(),
                func.count(case((AgentRun.status == "succeeded", 1))),
                func.coalesce(func.sum(AgentRun.input_tokens), 0),
                func.coalesce(func.sum(AgentRun.output_tokens), 0),
                func.coalesce(func.sum(AgentRun.estimated_cost), 0.0),
            ),
            AgentRun,
            principal,
        ).where(*in_range(AgentRun.started_at)),
    )
    calls, failed_calls = await _one(
        session,
        scoped(
            select(func.count(), func.count(case((AgentToolCall.status == "failed", 1)))),
            AgentToolCall,
            principal,
        ).where(*in_range(AgentToolCall.created_at)),
    )

    decisions, approved = await _one(
        session,
        scoped(
            select(func.count(), func.count(case((Approval.decision == "approved", 1)))),
            Approval,
            principal,
        ).where(*in_range(Approval.reviewed_at)),
    )

    mtta, mttr = await _one(
        session,
        scoped(
            select(
                func.avg(_seconds(Incident.acknowledged_at, Incident.started_at)),
                func.avg(_seconds(Incident.resolved_at, Incident.started_at)),
            ),
            Incident,
            principal,
        ).where(*in_range(Incident.started_at)),
    )

    return Evaluations(
        range_start=range_start,
        range_end=range_end,
        detection=DetectionMetrics(
            incidents=detected, delay_p50_seconds=_float(p50), delay_p95_seconds=_float(p95)
        ),
        investigations=InvestigationMetrics(
            total=total, succeeded=succeeded, partial=partial, failed=failed
        ),
        agents=AgentMetrics(
            runs=runs,
            success_rate=_ratio(ok_runs, runs),
            tool_calls=calls,
            tool_error_rate=_ratio(failed_calls, calls),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cost_usd=float(cost),
        ),
        remediation=RemediationMetrics(
            decisions=decisions, approval_rate=_ratio(approved, decisions)
        ),
        response=ResponseMetrics(mtta_seconds=_float(mtta), mttr_seconds=_float(mttr)),
    )
