"""GET /api/v1/evaluations: aggregate metrics, time range, and organization isolation."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import (
    AgentRun,
    AgentToolCall,
    AnomalyDetection,
    Approval,
    Incident,
    IncidentStatus,
    Investigation,
    InvestigationStatus,
    RemediationAction,
    RemediationProposal,
    Service,
    Severity,
)
from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory
) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(migrated_database_url, factory) as c:
        yield c


async def me(client: httpx.AsyncClient, caller: Caller) -> dict[str, Any]:
    response = await client.get("/api/v1/me", headers=caller.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def incident(org: uuid.UUID, service: Service | None, started: datetime, **extra: Any) -> Incident:
    return Incident(
        organization_id=org,
        service_id=service.id if service else None,
        title="High error rate",
        severity=Severity.HIGH,
        status=extra.pop("status", IncidentStatus.INVESTIGATING),
        source=extra.pop("source", "detector"),
        started_at=started,
        **extra,
    )


def detection(inc: Incident, window_start: datetime) -> AnomalyDetection:
    return AnomalyDetection(
        organization_id=inc.organization_id,
        service_id=inc.service_id,
        incident_id=inc.id,
        detector="error-rate",
        failure_category="high_error_rate",
        outcome="triggered",
        window_start=window_start,
        window_end=window_start + timedelta(minutes=1),
    )


async def seed(
    sessions: async_sessionmaker[AsyncSession], org: uuid.UUID, reviewer: uuid.UUID
) -> None:
    """Two detector incidents (delays 60 s and 120 s), runs, tool calls, and decisions."""
    async with sessions() as session:
        service = Service(organization_id=org, name="Checkout", slug=f"checkout-{org.hex[:6]}")
        session.add(service)
        await session.flush()
        first = incident(
            org,
            service,
            NOW - timedelta(hours=3),
            acknowledged_at=NOW - timedelta(hours=3) + timedelta(minutes=2),
            resolved_at=NOW - timedelta(hours=2),
            status=IncidentStatus.RESOLVED,
        )
        second = incident(
            org,
            service,
            NOW - timedelta(hours=1),
            acknowledged_at=NOW - timedelta(hours=1) + timedelta(minutes=6),
        )
        manual = incident(org, None, NOW - timedelta(hours=1), source="manual")
        old = incident(
            org,
            service,
            NOW - timedelta(days=60),
            acknowledged_at=NOW - timedelta(days=60) + timedelta(hours=9),
        )
        session.add_all([first, second, manual, old])
        await session.flush()
        session.add_all(
            [
                detection(first, first.started_at - timedelta(seconds=60)),
                # A later window on the same incident does not change its delay.
                detection(first, first.started_at + timedelta(minutes=5)),
                detection(second, second.started_at - timedelta(seconds=120)),
                detection(old, old.started_at - timedelta(hours=1)),
            ]
        )
        investigations = [
            Investigation(
                organization_id=org,
                incident_id=inc.id,
                requested_by="test",
                status=st,
                created_at=when,
            )
            for inc, st, when in [
                (first, InvestigationStatus.COMPLETED, NOW - timedelta(hours=3)),
                (second, InvestigationStatus.PARTIAL, NOW - timedelta(hours=1)),
                (manual, InvestigationStatus.COMPLETED, NOW - timedelta(minutes=30)),
                (old, InvestigationStatus.FAILED, NOW - timedelta(days=60)),
            ]
        ]
        session.add_all(investigations)
        await session.flush()
        runs = [
            AgentRun(
                organization_id=org,
                investigation_id=investigations[0].id,
                incident_id=first.id,
                agent_name="synthesis",
                status=st,
                model_provider="scripted",
                model_name="scripted",
                prompt_version="v2",
                input_tokens=tokens,
                output_tokens=tokens // 10,
                estimated_cost=cost,
                started_at=when,
            )
            for st, tokens, cost, when in [
                ("succeeded", 1000, 0.01, NOW - timedelta(hours=3)),
                ("succeeded", 2000, 0.02, NOW - timedelta(hours=3)),
                ("fallback", 0, 0.0, NOW - timedelta(hours=1)),
                ("succeeded", 5000, 5.0, NOW - timedelta(days=60)),
            ]
        ]
        session.add_all(runs)
        await session.flush()
        session.add_all(
            AgentToolCall(
                organization_id=org,
                agent_run_id=runs[0].id,
                tool_name="query_service_metrics",
                arguments={},
                status=st,
                created_at=NOW - timedelta(hours=2),
            )
            for st in ("succeeded", "succeeded", "succeeded", "failed")
        )
        for decision, when in [
            ("approved", NOW - timedelta(hours=2)),
            ("approved", NOW - timedelta(hours=1)),
            ("rejected", NOW - timedelta(minutes=10)),
            ("rejected", NOW - timedelta(days=50)),
        ]:
            proposal = RemediationProposal(
                organization_id=org,
                incident_id=first.id,
                action_type=RemediationAction.RESTART_DEPLOYMENT,
                description="restart",
                parameters={},
                risk_level="medium",
                verification_plan={},
            )
            session.add(proposal)
            await session.flush()
            session.add(
                Approval(
                    organization_id=org,
                    proposal_id=proposal.id,
                    proposal_version=1,
                    requested_by="agent:remediation",
                    requested_at=when,
                    reviewed_by=reviewer,
                    reviewer_name="Cleo",
                    decision=decision,
                    reviewed_at=when,
                )
            )
        await session.commit()


async def test_metrics_are_aggregated_over_the_default_range(
    client: httpx.AsyncClient,
    factory: TokenFactory,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    viewer = Caller(factory, new_org(), "viewer")
    profile = await me(client, viewer)
    await seed(sessions, uuid.UUID(profile["organization"]["id"]), uuid.UUID(profile["id"]))

    response = await client.get("/api/v1/evaluations", headers=viewer.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["detection"] == {
        "incidents": 2,
        "delay_p50_seconds": pytest.approx(90.0),
        "delay_p95_seconds": pytest.approx(117.0),
    }
    assert body["investigations"] == {"total": 3, "succeeded": 2, "partial": 1, "failed": 0}
    agents = body["agents"]
    assert agents["runs"] == 3
    assert agents["success_rate"] == pytest.approx(2 / 3)
    assert agents["tool_calls"] == 4
    assert agents["tool_error_rate"] == pytest.approx(0.25)
    assert (agents["input_tokens"], agents["output_tokens"]) == (3000, 300)
    assert agents["cost_usd"] == pytest.approx(0.03)
    assert body["remediation"] == {"decisions": 3, "approval_rate": pytest.approx(2 / 3)}
    # MTTA over the 2 acknowledged incidents in range: (2 + 6) / 2 minutes; MTTR: 1 hour.
    assert body["response"]["mtta_seconds"] == pytest.approx(240.0)
    assert body["response"]["mttr_seconds"] == pytest.approx(3600.0)


async def test_an_explicit_range_selects_older_activity(
    client: httpx.AsyncClient,
    factory: TokenFactory,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    viewer = Caller(factory, new_org(), "viewer")
    profile = await me(client, viewer)
    await seed(sessions, uuid.UUID(profile["organization"]["id"]), uuid.UUID(profile["id"]))

    response = await client.get(
        "/api/v1/evaluations",
        params={
            "from": (NOW - timedelta(days=70)).isoformat(),
            "to": (NOW - timedelta(days=40)).isoformat(),
        },
        headers=viewer.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["detection"]["delay_p50_seconds"] == pytest.approx(3600.0)
    assert body["investigations"]["failed"] == 1
    assert body["agents"]["input_tokens"] == 5000
    assert body["remediation"] == {"decisions": 1, "approval_rate": 0.0}
    assert body["response"]["mttr_seconds"] is None


async def test_an_empty_organization_has_no_rates(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    response = await client.get(
        "/api/v1/evaluations", headers=Caller(factory, new_org(), "viewer").headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agents"]["success_rate"] is None
    assert body["agents"]["tool_error_rate"] is None
    assert body["remediation"]["approval_rate"] is None
    assert body["detection"]["delay_p50_seconds"] is None


async def test_other_organizations_activity_is_never_counted(
    client: httpx.AsyncClient,
    factory: TokenFactory,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    other = Caller(factory, new_org(), "administrator")
    profile = await me(client, other)
    await seed(sessions, uuid.UUID(profile["organization"]["id"]), uuid.UUID(profile["id"]))

    response = await client.get(
        "/api/v1/evaluations", headers=Caller(factory, new_org(), "administrator").headers
    )

    body = response.json()
    assert body["investigations"]["total"] == 0
    assert body["agents"]["runs"] == 0
    assert body["remediation"]["decisions"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-01-02T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        {"from": "2024-01-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        {"from": "2026-01-01T00:00:00"},
    ],
)
async def test_invalid_ranges_are_rejected(
    client: httpx.AsyncClient, factory: TokenFactory, params: dict[str, str]
) -> None:
    response = await client.get(
        "/api/v1/evaluations", params=params, headers=Caller(factory, new_org(), "viewer").headers
    )

    assert response.status_code == 422


async def test_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/evaluations")).status_code == 401


async def test_requires_an_application_role(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    response = await client.get("/api/v1/evaluations", headers=Caller(factory, new_org()).headers)

    assert response.status_code == 403
