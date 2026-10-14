"""Postmortem drafting: grounded findings, deterministic timeline, template fallback, API."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opspilot_api.agents.llm import LLMError, ScriptedLLM
from opspilot_api.agents.postmortem import generate, pending
from opspilot_api.db.models import Evidence, Incident
from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory
) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(migrated_database_url, factory) as c:
        yield c


async def resolved_incident(
    client: httpx.AsyncClient, caller: Caller, sessions: async_sessionmaker[AsyncSession]
) -> str:
    incident = (
        await client.post(
            "/api/v1/incidents",
            json={"title": "Checkout errors", "severity": "high"},
            headers=caller.headers,
        )
    ).json()
    url = f"/api/v1/incidents/{incident['id']}"
    step = await client.post(f"{url}/investigate", json={"version": 1}, headers=caller.headers)
    step = await client.patch(
        url,
        json={"version": step.json()["version"], "status": "MONITORING"},
        headers=caller.headers,
    )
    await client.post(
        f"{url}/resolve", json={"version": step.json()["version"]}, headers=caller.headers
    )
    async with sessions() as session:
        db_incident = await session.get_one(Incident, uuid.UUID(incident["id"]))
        collected = datetime.now(UTC)
        for i, summary in enumerate(
            ("error rate 45% on checkout", "revision 7 (1.4.2) rolled out 2 minutes before")
        ):
            session.add(
                Evidence(
                    organization_id=db_incident.organization_id,
                    incident_id=db_incident.id,
                    evidence_type="metrics",
                    source="prometheus",
                    summary=summary,
                    confidence=0.9,
                    # One transaction gives both rows the same now(); E1/E2 follow this order.
                    created_at=collected + timedelta(seconds=i),
                )
            )
        await session.commit()
    return str(incident["id"])


def model(answer: dict[str, Any] | None) -> ScriptedLLM:
    def respond(schema: type[BaseModel], prompt: str) -> dict[str, Any]:
        if answer is None:
            raise LLMError("down")
        return answer

    return ScriptedLLM(respond)


DRAFT = {
    "summary": "Release 1.4.2 broke checkout.",
    "impact": "Half of checkouts failed.",
    "root_cause": {
        "statement": "Release 1.4.2",
        "certainty": "strong_hypothesis",
        "evidence": ["E2"],
    },
    "findings": [
        {"statement": "Error rate reached 45%", "certainty": "confirmed", "evidence": ["E1"]},
        {"statement": "The database was slow", "certainty": "confirmed", "evidence": ["E9"]},
    ],
    "resolution": "Rolled back.",
    "follow_ups": ["Add a canary"],
}


async def test_findings_must_cite_collected_evidence(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    incident_id = await resolved_incident(client, Caller(factory, new_org(), "operator"), sessions)

    postmortem = await generate(sessions, model(DRAFT), uuid.UUID(incident_id))

    content = postmortem.content or {}
    assert content["root_cause"]["certainty"] == "strong_hypothesis"
    assert content["findings"][1] == {
        "statement": "The database was slow",
        "certainty": "unknown",
        "evidence": [],
    }
    assert [t["event"] for t in content["timeline"]][:2] == [
        "Incident detected",
        "Detected → Investigating",
    ]
    assert content["evidence"]["E1"]["summary"] == "error rate 45% on checkout"
    assert postmortem.generated_by == "scripted:scripted"


async def test_a_template_is_stored_when_the_model_fails(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    incident_id = await resolved_incident(client, Caller(factory, new_org(), "operator"), sessions)

    postmortem = await generate(sessions, model(None), uuid.UUID(incident_id))

    assert postmortem.generated_by == "template"
    assert postmortem.content is not None
    assert postmortem.content["root_cause"]["certainty"] == "unknown"
    assert len(postmortem.content["findings"]) == 2


async def test_resolved_incidents_without_a_postmortem_are_pending(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    incident_id = uuid.UUID(
        await resolved_incident(client, Caller(factory, new_org(), "operator"), sessions)
    )

    assert incident_id in await pending(sessions, limit=500)
    await generate(sessions, model(DRAFT), incident_id)
    assert incident_id not in await pending(sessions, limit=500)


async def test_api_reads_and_requests_regeneration(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident_id = await resolved_incident(client, operator, sessions)
    viewer = Caller(factory, operator.org, "viewer")

    missing = await client.get(
        f"/api/v1/incidents/{incident_id}/postmortem", headers=viewer.headers
    )
    await generate(sessions, model(DRAFT), uuid.UUID(incident_id))
    ready = await client.get(f"/api/v1/incidents/{incident_id}/postmortem", headers=viewer.headers)
    forbidden = await client.post(
        f"/api/v1/incidents/{incident_id}/postmortem", headers=viewer.headers
    )
    again = await client.post(
        f"/api/v1/incidents/{incident_id}/postmortem", headers=operator.headers
    )
    outsider = await client.get(
        f"/api/v1/incidents/{incident_id}/postmortem",
        headers=Caller(factory, new_org(), "administrator").headers,
    )

    assert missing.status_code == 404
    assert ready.json()["content"]["summary"] == "Release 1.4.2 broke checkout."
    assert forbidden.status_code == 403
    assert (again.status_code, again.json()["status"]) == (202, "pending")
    assert outsider.status_code == 404


async def test_open_incidents_cannot_request_a_postmortem(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident = (
        await client.post(
            "/api/v1/incidents", json={"title": "Open", "severity": "low"}, headers=operator.headers
        )
    ).json()

    response = await client.post(
        f"/api/v1/incidents/{incident['id']}/postmortem", headers=operator.headers
    )

    assert response.status_code == 409
