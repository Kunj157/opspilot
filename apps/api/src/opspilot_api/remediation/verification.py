"""Deterministic recovery verification after a remediation ran.

Each check is a short, non-blocking look at one execution:

1. Wait for the rollout to complete with every pod ready; a stalled rollout
   (progress deadline exceeded, or not done within the rollout timeout) fails.
2. Once complete, wait one verification window, then measure the error rate
   and p95 latency over that window and compare them with the plan's limits
   and the pre-incident baseline.
3. Pass: the incident is resolved. Fail: the investigation reopens.

If telemetry stays unavailable past the deadline, verification fails safe to
manual review rather than resolving blind.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.audit.service import record
from opspilot_api.db.models import (
    ActorType,
    ExecutionStatus,
    Incident,
    IncidentStatus,
    RemediationExecution,
    RemediationProposal,
)
from opspilot_api.incidents import service as incidents
from opspilot_api.kube import KubeReader, RolloutStatus
from opspilot_api.remediation.executor import reopen
from opspilot_api.telemetry import MetricsProvider, TelemetryUnavailable, label_value

log = structlog.get_logger("opspilot.verification")

ACTOR_ID = "worker:verification"
DEFAULTS: dict[str, Any] = {
    "window_minutes": 3,
    "max_error_rate": 0.02,
    "max_p95_ratio_to_baseline": 1.5,
    "rollout_timeout_minutes": 5,
}
# How long telemetry may stay unavailable after the window before failing safe.
TELEMETRY_GRACE = timedelta(minutes=5)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str
    measurements: dict[str, Any]


async def pending(
    sessions: async_sessionmaker[AsyncSession], *, completed_before: datetime | None = None
) -> list[uuid.UUID]:
    """Executions awaiting verification; `completed_before` leaves the first look to the event."""
    async with sessions() as session:
        rows = await session.scalars(
            select(RemediationExecution.id)
            .join(Incident, Incident.id == RemediationExecution.incident_id)
            .where(
                RemediationExecution.status == ExecutionStatus.SUCCEEDED,
                RemediationExecution.verification_status == "pending",
                Incident.status == IncidentStatus.VERIFYING,
                *(
                    [RemediationExecution.completed_at < completed_before]
                    if completed_before
                    else []
                ),
            )
            .order_by(RemediationExecution.completed_at)
        )
        return list(rows)


def _selector(parameters: dict[str, Any]) -> str:
    return (
        f"namespace={label_value(parameters['namespace'])},"
        f"service={label_value(parameters['deployment'])}"
    )


async def _scalar(metrics: MetricsProvider, promql: str, at: datetime) -> float | None:
    samples = await metrics.query(promql, at)
    return samples[0].value if samples else None


async def _window(
    metrics: MetricsProvider, parameters: dict[str, Any], end: datetime, minutes: int
) -> dict[str, float | None]:
    """Error rate and p95 latency over the `minutes` ending at `end`."""
    sel, w = _selector(parameters), f"{minutes}m"
    requests = await _scalar(metrics, f"sum(increase(http_requests_total{{{sel}}}[{w}]))", end)
    errors = await _scalar(metrics, f"sum(increase(http_errors_total{{{sel}}}[{w}]))", end)
    p95 = await _scalar(
        metrics,
        "histogram_quantile(0.95, sum by (le) "
        f"(rate(http_request_duration_seconds_bucket{{{sel}}}[{w}])))",
        end,
    )
    rate = (errors or 0.0) / requests if requests else None
    return {"requests": requests, "error_rate": rate, "p95_seconds": p95}


def _judge(plan: dict[str, Any], now: dict[str, Any], baseline: dict[str, Any]) -> Verdict:
    measurements = {"window": now, "baseline": baseline}
    rate, p95, base_p95 = now["error_rate"], now["p95_seconds"], baseline["p95_seconds"]
    if rate is None:
        return Verdict(False, "no traffic during the verification window", measurements)
    if rate > plan["max_error_rate"]:
        return Verdict(
            False,
            f"error rate {rate:.1%} is above {plan['max_error_rate']:.0%}",
            measurements,
        )
    limit = plan["max_p95_ratio_to_baseline"]
    if p95 is not None and base_p95 and p95 > base_p95 * limit:
        return Verdict(
            False,
            f"p95 {p95 * 1000:.0f} ms is above {limit}x the baseline {base_p95 * 1000:.0f} ms",
            measurements,
        )
    latency = f", p95 {p95 * 1000:.0f} ms" if p95 is not None else ""
    return Verdict(True, f"error rate {rate:.1%}{latency}", measurements)


def _stalled(status: RolloutStatus) -> bool:
    return any(c.startswith("Progressing=False") for c in status.conditions)


async def verify(
    sessions: async_sessionmaker[AsyncSession],
    kube: KubeReader,
    metrics: MetricsProvider,
    execution_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Verdict | None:
    """One look at one execution: a verdict once decided, None while waiting."""
    now = now or datetime.now(UTC)
    async with sessions() as session:
        execution = await session.get_one(RemediationExecution, execution_id)
        if execution.verification_status != "pending":
            return None
        proposal = await session.get_one(RemediationProposal, execution.proposal_id)
        incident = await session.get_one(Incident, execution.incident_id)
    plan = {**DEFAULTS, **proposal.verification_plan}
    parameters = proposal.parameters
    finished = execution.completed_at or now

    # 1. The rollout.
    if execution.rollout_completed_at is None:
        try:
            status = await kube.rollout_status(parameters["namespace"], parameters["deployment"])
        except Exception as exc:
            if now - finished > timedelta(minutes=plan["rollout_timeout_minutes"]):
                return await _decide(
                    sessions,
                    execution_id,
                    Verdict(False, f"rollout status unavailable: {exc}", {}),
                )
            return None
        rollout = {"ready": status.ready, "desired": status.desired, "complete": status.complete}
        if _stalled(status):
            return await _decide(
                sessions, execution_id, Verdict(False, "the rollout stalled", {"rollout": rollout})
            )
        if not (status.complete and status.ready == status.desired):
            if now - finished > timedelta(minutes=plan["rollout_timeout_minutes"]):
                return await _decide(
                    sessions,
                    execution_id,
                    Verdict(False, "the rollout did not complete in time", {"rollout": rollout}),
                )
            return None
        async with sessions() as session:
            execution = await session.get_one(RemediationExecution, execution_id)
            execution.rollout_completed_at = now
            execution.verification = {"rollout": rollout}
            await session.commit()
        return None

    # 2. One full window of traffic after the rollout.
    window = int(plan["window_minutes"])
    window_end = execution.rollout_completed_at + timedelta(minutes=window)
    if now < window_end:
        return None
    baseline_end = incident.started_at - timedelta(minutes=1)
    try:
        current = await _window(metrics, parameters, window_end, window)
        baseline = await _window(metrics, parameters, baseline_end, window)
    except TelemetryUnavailable as exc:
        if now - window_end > TELEMETRY_GRACE:
            return await _decide(
                sessions,
                execution_id,
                Verdict(False, f"telemetry unavailable, manual review needed: {exc}", {}),
            )
        return None

    # 3. The verdict.
    verdict = _judge(plan, current, baseline)
    return await _decide(sessions, execution_id, verdict)


async def _decide(
    sessions: async_sessionmaker[AsyncSession], execution_id: uuid.UUID, verdict: Verdict
) -> Verdict:
    async with sessions() as session:
        execution = await session.get_one(RemediationExecution, execution_id, with_for_update=True)
        if execution.verification_status != "pending":
            return verdict
        incident = await session.get_one(Incident, execution.incident_id)
        execution.verification_status = "passed" if verdict.passed else "failed"
        execution.verification = {
            **execution.verification,
            **verdict.measurements,
            "reason": verdict.reason,
        }
        execution.verified_at = datetime.now(UTC)
        actor = incidents.Actor(ActorType.SYSTEM, ACTOR_ID, incident.organization_id)
        metadata = {
            "execution_id": str(execution.id),
            "proposal_id": str(execution.proposal_id),
            "reason": verdict.reason,
            **verdict.measurements,
        }
        await incidents.note(
            session,
            incident,
            actor,
            event_type="incident.verification_passed"
            if verdict.passed
            else "incident.verification_failed",
            title=(
                f"Recovery verified: {verdict.reason}"
                if verdict.passed
                else f"Verification failed: {verdict.reason}"
            ),
            metadata=metadata,
        )
        await record(
            session,
            organization_id=incident.organization_id,
            actor_type=ActorType.SYSTEM,
            actor_id=ACTOR_ID,
            action="remediation.verified" if verdict.passed else "remediation.verification_failed",
            resource_type="remediation_proposal",
            resource_id=str(execution.proposal_id),
            metadata=metadata,
        )
        if incident.status is IncidentStatus.VERIFYING:
            if verdict.passed:
                await incidents.transition(
                    session,
                    incident,
                    IncidentStatus.RESOLVED,
                    expected_version=incident.version,
                    actor=actor,
                    reason="recovery verified",
                )
            else:
                await reopen(session, incident, actor, f"verification failed: {verdict.reason}")
        await session.commit()
    log.info("verification finished", execution_id=str(execution_id), passed=verdict.passed)
    return verdict
