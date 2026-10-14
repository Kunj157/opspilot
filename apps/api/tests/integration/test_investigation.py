"""The investigation workflow end to end: real database, fake telemetry, scripted model."""

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opspilot_api.agents.investigation import Investigator, Limits
from opspilot_api.agents.llm import LLMError, ScriptedLLM
from opspilot_api.agents.queue import enqueue
from opspilot_api.agents.schemas import ProposalDraft, Synthesis, ToolPlan, TriageOutput
from opspilot_api.agents.tools import ServiceTarget, ToolContext
from opspilot_api.db.models import (
    AgentRun,
    AgentToolCall,
    Evidence,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Investigation,
    InvestigationStatus,
    Organization,
    ProposalStatus,
    RemediationAction,
    RemediationProposal,
    Service,
    Severity,
)
from opspilot_api.kube import Revision, RolloutStatus, check_namespace
from opspilot_api.telemetry import LogLine, Sample, Series, Span, TraceDetail, TraceSummary

pytestmark = pytest.mark.integration
NOW = datetime.now(UTC)


class Metrics:
    async def query(self, promql: str, at: datetime) -> list[Sample]:
        recent = at > NOW - timedelta(minutes=1)
        if "http_errors_total" in promql:
            return [Sample({}, 0.5)] if recent and "checkout" in promql else []
        if "duration" in promql:
            return [Sample({}, 0.05)]
        return [Sample({}, 1.0)]

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: timedelta
    ) -> list[Series]:
        return []


class Logs:
    async def search(self, logql: str, start: datetime, end: datetime, limit: int) -> list[LogLine]:
        labels = {"route": "/orders", "status": "500", "trace_id": "t1", "level": "error"}
        return [LogLine(NOW, "request served", labels)] * 4


class Traces:
    async def search(
        self, service: str, start: datetime, end: datetime, limit: int, *, errors_only: bool = False
    ) -> list[TraceSummary]:
        return [TraceSummary("t1", "storefront", "POST /api/checkout", NOW, 30.0)]

    async def get(self, trace_id: str) -> TraceDetail | None:
        return TraceDetail(
            trace_id,
            [
                Span(
                    "checkout",
                    "POST /orders",
                    "SPAN_KIND_SERVER",
                    9.0,
                    True,
                    {"error.type": "InjectedFault"},
                )
            ],
        )


class Kube:
    async def rollout_history(self, namespace: str, deployment: str) -> list[Revision]:
        check_namespace(namespace, frozenset({"demo"}))
        return [
            Revision(7, NOW - timedelta(minutes=4), "release checkout 1.4.2", "1.4.2", "img"),
            Revision(6, NOW - timedelta(days=1), "chart release 1", "1.0.0", "img"),
        ]

    async def rollout_status(self, namespace: str, deployment: str) -> RolloutStatus:
        return RolloutStatus(2, 2, 2, 2, True, [])


def happy_model(
    *,
    synthesis: dict[str, Any] | None = None,
    proposal: dict[str, Any] | None = None,
    fail: set[type[BaseModel]] | None = None,
) -> Callable[[type[BaseModel], str], dict[str, Any]]:
    def answer(schema: type[BaseModel], prompt: str) -> dict[str, Any]:
        if fail and schema in fail:
            raise LLMError("model unavailable")
        if schema is TriageOutput:
            return {
                "suspected_service": "checkout",
                "reasoning": "errors are on checkout",
                "focus": ["errors"],
            }
        if schema is ToolPlan:
            return {"calls": []}  # use the default plan
        if schema is Synthesis:
            return synthesis or {
                "summary": "Checkout 1.4.2 fails half of orders since its rollout.",
                "hypotheses": [
                    {
                        "description": "Release 1.4.2 broke checkout",
                        "confidence": 0.9,
                        "supporting_evidence": ["E3", "E6"],
                        "contradicting_evidence": [],
                    }
                ],
                "unknowns": ["why 1.4.2 fails"],
                "enough_evidence": True,
            }
        if schema is ProposalDraft:
            return proposal or {
                "action_type": "ROLLBACK_DEPLOYMENT",
                "target_service": "checkout",
                "reason": "Errors began with release 1.4.2",
                "evidence": ["E3", "E6"],
            }
        raise AssertionError(schema)

    return answer


@pytest.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def setup(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.flush()
        checkout = Service(
            organization_id=org.id,
            name="Checkout",
            slug="checkout",
            namespace="demo",
            deployment_name="checkout",
        )
        session.add(checkout)
        await session.flush()
        incident = Incident(
            organization_id=org.id,
            service_id=checkout.id,
            title="High error rate on Checkout",
            severity=Severity.CRITICAL,
            source="detector",
        )
        session.add(incident)
        await session.flush()
        investigation, _ = await enqueue(session, incident, "system")
        await session.commit()
        return investigation.id


def investigator(
    sessions: async_sessionmaker[AsyncSession], model: Any, limits: Limits | None = None
) -> Investigator:
    async def make_context(organization_id: uuid.UUID, incident_id: uuid.UUID) -> ToolContext:
        async def resolve(slug: str) -> ServiceTarget | None:
            async with sessions() as session:
                s = await session.scalar(
                    sa.select(Service).where(
                        Service.organization_id == organization_id, Service.slug == slug
                    )
                )
            return (
                ServiceTarget(str(s.id), s.slug, s.name, s.namespace, s.deployment_name)
                if s
                else None
            )

        return ToolContext(
            organization_id,
            datetime.now(UTC),
            resolve,
            Metrics(),
            Logs(),
            Traces(),
            Kube(),
            frozenset({"demo"}),
            sessions=sessions,
            incident_id=incident_id,
        )

    return Investigator(sessions, ScriptedLLM(model), make_context, limits=limits)


async def load(
    sessions: async_sessionmaker[AsyncSession], investigation_id: uuid.UUID
) -> dict[str, Any]:
    async with sessions() as session:
        inv = await session.get_one(Investigation, investigation_id)
        return {
            "investigation": inv,
            "incident": await session.get_one(Incident, inv.incident_id),
            "evidence": list(
                await session.scalars(
                    sa.select(Evidence).where(Evidence.investigation_id == inv.id)
                )
            ),
            "proposals": list(
                await session.scalars(
                    sa.select(RemediationProposal).where(
                        RemediationProposal.incident_id == inv.incident_id
                    )
                )
            ),
            "runs": list(
                await session.scalars(
                    sa.select(AgentRun).where(AgentRun.investigation_id == inv.id)
                )
            ),
            "calls": list(
                await session.scalars(
                    sa.select(AgentToolCall)
                    .join(AgentRun)
                    .where(AgentRun.investigation_id == inv.id)
                )
            ),
            "events": list(
                await session.scalars(
                    sa.select(IncidentEvent.event_type)
                    .where(IncidentEvent.incident_id == inv.incident_id)
                    .order_by(IncidentEvent.sequence)
                )
            ),
        }


async def test_a_bad_release_is_investigated_and_a_rollback_proposed(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    investigation_id = await setup(sessions)

    status = await investigator(sessions, happy_model()).run(investigation_id)

    data = await load(sessions, investigation_id)
    assert status is InvestigationStatus.COMPLETED
    [proposal] = data["proposals"]
    assert proposal.action_type is RemediationAction.ROLLBACK_DEPLOYMENT
    assert proposal.status is ProposalStatus.PENDING
    assert proposal.parameters == {
        "namespace": "demo",
        "deployment": "checkout",
        "to_revision": 6,
        "from_version": "1.4.2",
        "to_version": "1.0.0",
    }
    evidence_ids = {str(e.id) for e in data["evidence"]}
    assert set(proposal.evidence_ids) <= evidence_ids
    assert data["incident"].status is IncidentStatus.AWAITING_APPROVAL
    assert {e.source for e in data["evidence"]} >= {"prometheus", "loki", "tempo", "kubernetes"}
    assert {r.agent_name for r in data["runs"]} == {
        "triage",
        "observability",
        "deployment",
        "runbook",
        "synthesis",
        "remediation",
    }
    assert all(r.prompt_version == "v1" for r in data["runs"])
    assert "incident.remediation_proposed" in data["events"]
    assert data["events"][-1] == "incident.investigation_finished"
    result = data["investigation"].result
    assert result["hypotheses"][0]["supporting_evidence"] == ["E3", "E6"]
    assert result["manual_review"] is False


async def test_model_failure_keeps_evidence_and_proposes_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    investigation_id = await setup(sessions)

    status = await investigator(
        sessions, happy_model(fail={TriageOutput, ToolPlan, Synthesis})
    ).run(investigation_id)

    data = await load(sessions, investigation_id)
    assert status is InvestigationStatus.PARTIAL
    assert data["evidence"], "fixed tool plans still collect evidence"
    assert data["proposals"] == []
    assert data["investigation"].result["manual_review"] is True
    assert {r.status for r in data["runs"] if r.agent_name == "synthesis"} == {"fallback"}


async def test_ungrounded_hypotheses_are_dropped_and_the_run_stops_at_max_rounds(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    investigation_id = await setup(sessions)
    made_up = {
        "summary": "Probably the database.",
        "hypotheses": [
            {"description": "Database outage", "confidence": 0.95, "supporting_evidence": ["E99"]}
        ],
        "enough_evidence": True,
    }

    status = await investigator(sessions, happy_model(synthesis=made_up), Limits(max_rounds=2)).run(
        investigation_id
    )

    data = await load(sessions, investigation_id)
    assert status is InvestigationStatus.PARTIAL
    assert data["investigation"].round == 1
    assert data["investigation"].result["hypotheses"] == []
    assert data["proposals"] == []


async def test_policy_rejects_targets_outside_the_catalog(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    investigation_id = await setup(sessions)
    bad = {
        "action_type": "RESTART_DEPLOYMENT",
        "target_service": "coredns",
        "reason": "restart dns",
        "evidence": ["E3"],
    }

    status = await investigator(sessions, happy_model(proposal=bad)).run(investigation_id)

    data = await load(sessions, investigation_id)
    assert status is InvestigationStatus.COMPLETED
    assert data["proposals"] == []
    assert any("rejected by policy" in n for n in data["investigation"].result["notes"])
    assert data["incident"].status is IncidentStatus.INVESTIGATING


async def test_actions_outside_the_allow_list_never_reach_storage(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    investigation_id = await setup(sessions)
    evil = {
        "action_type": "DELETE_NAMESPACE",
        "target_service": "checkout",
        "reason": "x",
        "evidence": ["E3"],
    }

    await investigator(sessions, happy_model(proposal=evil)).run(investigation_id)

    assert (await load(sessions, investigation_id))["proposals"] == []


async def test_the_tool_call_limit_stops_the_run(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    investigation_id = await setup(sessions)

    status = await investigator(sessions, happy_model(), Limits(max_tool_calls=3)).run(
        investigation_id
    )

    data = await load(sessions, investigation_id)
    assert status is InvestigationStatus.PARTIAL
    assert data["investigation"].error == "tool call limit reached"
    assert len(data["calls"]) == 3


async def test_a_restarted_worker_resumes_at_the_next_node(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    investigation_id = await setup(sessions)
    crashing = investigator(sessions, happy_model())

    async def crash(state: Any) -> Any:
        raise RuntimeError("worker died")

    crashing._runbook = crash  # type: ignore[method-assign]
    crashing.graph = crashing._build()
    with pytest.raises(RuntimeError):
        await crashing.run(investigation_id)
    before = await load(sessions, investigation_id)
    assert before["investigation"].current_node == "deployment"

    status = await investigator(sessions, happy_model()).run(investigation_id)

    after = await load(sessions, investigation_id)
    assert status is InvestigationStatus.COMPLETED
    triage_calls = [c for c in after["calls"] if c.tool_name == "get_service_dependencies"]
    assert len(triage_calls) == 1, "completed nodes are not repeated"
