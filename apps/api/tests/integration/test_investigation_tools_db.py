"""Database-backed investigation tools: dependencies, history, runbooks, tenancy."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opspilot_api.agents.tools import ServiceTarget, ToolContext, run_tool
from opspilot_api.db.models import (
    HealthStatus,
    Incident,
    Organization,
    Runbook,
    RunbookStatus,
    Service,
    ServiceDependency,
    Severity,
)
from opspilot_api.runbooks.embeddings import HashingEmbedder
from opspilot_api.runbooks.ingest import ingest

pytestmark = pytest.mark.integration

RUNBOOK = """---
title: Checkout high error rate
services: [checkout]
version: 1
---

## Symptoms

Checkout returns HTTP 500 after a release.

## Safe actions

Roll back checkout.
"""


@pytest.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def world(sessions: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        other = Organization(name="Other", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add_all([org, other])
        await session.flush()
        storefront = Service(organization_id=org.id, name="Storefront", slug="storefront")
        checkout = Service(
            organization_id=org.id,
            name="Checkout",
            slug="checkout",
            health_status=HealthStatus.CRITICAL,
        )
        payment = Service(organization_id=org.id, name="Payment", slug="payment")
        foreign = Service(organization_id=other.id, name="Checkout", slug="checkout")
        session.add_all([storefront, checkout, payment, foreign])
        await session.flush()
        session.add_all(
            [
                ServiceDependency(
                    organization_id=org.id,
                    source_service_id=storefront.id,
                    target_service_id=checkout.id,
                ),
                ServiceDependency(
                    organization_id=org.id,
                    source_service_id=checkout.id,
                    target_service_id=payment.id,
                ),
                Incident(
                    organization_id=org.id,
                    service_id=checkout.id,
                    title="Checkout 500s last week",
                    severity=Severity.HIGH,
                    source="manual",
                ),
                Incident(
                    organization_id=other.id,
                    service_id=foreign.id,
                    title="Foreign incident",
                    severity=Severity.LOW,
                    source="manual",
                ),
            ]
        )
        runbook = Runbook(
            organization_id=org.id,
            slug="checkout-high-error-rate",
            title="Checkout high error rate",
            services=["checkout"],
            content=RUNBOOK,
            content_hash="x",
            version=1,
        )
        session.add(runbook)
        await session.flush()
        await ingest(session, runbook, HashingEmbedder())
        await session.commit()
    return {"org": org, "checkout": checkout}


def context(
    sessions: async_sessionmaker[AsyncSession], org_id: uuid.UUID, checkout: Service
) -> ToolContext:
    async def resolve(slug: str) -> ServiceTarget | None:
        if slug != "checkout":
            return None
        return ServiceTarget(str(checkout.id), "checkout", "Checkout", None, None)

    return ToolContext(
        organization_id=org_id,
        now=datetime.now(UTC),
        resolve_service=resolve,
        metrics=None,  # type: ignore[arg-type]
        logs=None,  # type: ignore[arg-type]
        traces=None,  # type: ignore[arg-type]
        kube=None,  # type: ignore[arg-type]
        allowed_namespaces=frozenset({"demo"}),
        sessions=sessions,
        embedder=HashingEmbedder(),
    )


async def test_dependencies_list_callers_and_callees_with_health(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    w = await world(sessions)

    result = await run_tool(
        context(sessions, w["org"].id, w["checkout"]),
        "get_service_dependencies",
        {"service": "checkout"},
    )

    assert result.ok, result.error
    assert result.data["calls"] == [{"service": "payment", "health": "unknown"}]
    assert result.data["called_by"] == [{"service": "storefront", "health": "unknown"}]


async def test_similar_incidents_stay_inside_the_organization(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    w = await world(sessions)

    result = await run_tool(
        context(sessions, w["org"].id, w["checkout"]),
        "search_similar_incidents",
        {"service": "checkout"},
    )

    assert [i["title"] for i in result.data["incidents"]] == ["Checkout 500s last week"]


async def test_runbook_search_returns_cited_untrusted_excerpts(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    w = await world(sessions)

    result = await run_tool(
        context(sessions, w["org"].id, w["checkout"]),
        "search_runbooks",
        {"query": "checkout returns 500 after a release", "service": "checkout"},
    )

    assert result.ok, result.error
    assert result.data["runbooks"][0]["slug"] == "checkout-high-error-rate"
    assert "UNTRUSTED" in result.data["excerpts"]
    assert result.evidence is not None
    assert result.evidence.source == "runbook library"


async def test_runbook_search_only_uses_runbooks_for_the_worker_environment(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    w = await world(sessions)
    async with sessions() as session:
        await session.execute(
            update(Runbook)
            .where(Runbook.organization_id == w["org"].id)
            .values(environment="production")
        )
        await session.commit()
    ctx = context(sessions, w["org"].id, w["checkout"])
    args = {"query": "checkout returns 500 after a release", "service": "checkout"}

    staging = await run_tool(replace(ctx, environment="staging"), "search_runbooks", args)
    production = await run_tool(replace(ctx, environment="production"), "search_runbooks", args)

    assert not staging.ok
    assert staging.error == "no runbook matched"
    assert production.ok, production.error


async def test_get_runbook_returns_the_whole_runbook_quoted_and_cited(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    w = await world(sessions)
    ctx = context(sessions, w["org"].id, w["checkout"])

    by_slug = await run_tool(ctx, "get_runbook", {"runbook": "checkout-high-error-rate"})
    by_id = await run_tool(ctx, "get_runbook", {"runbook": by_slug.data["runbook"]["runbook_id"]})

    assert by_slug.ok, by_slug.error
    assert by_slug.data["sections"] == ["Symptoms", "Safe actions"]
    assert "UNTRUSTED" in by_slug.data["content"]
    assert "> Roll back checkout." in by_slug.data["content"]
    assert by_slug.data["runbook"]["version"] == 1
    assert by_slug.evidence is not None
    assert by_slug.evidence.query == "runbook checkout-high-error-rate v1"
    assert by_id.ok
    assert by_id.data["runbook"] == by_slug.data["runbook"]


async def test_get_runbook_refuses_versions_other_organizations_and_archived_runbooks(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    w = await world(sessions)
    other = await world(sessions)
    ctx = context(sessions, w["org"].id, w["checkout"])

    old = await run_tool(ctx, "get_runbook", {"runbook": "checkout-high-error-rate", "version": 3})
    foreign_id = await run_tool(
        context(sessions, other["org"].id, other["checkout"]),
        "get_runbook",
        {"runbook": "checkout-high-error-rate"},
    )
    async with sessions() as session:
        await session.execute(
            update(Runbook)
            .where(Runbook.organization_id == w["org"].id)
            .values(status=RunbookStatus.ARCHIVED)
        )
        await session.commit()
    stolen = await run_tool(
        ctx, "get_runbook", {"runbook": foreign_id.data["runbook"]["runbook_id"]}
    )
    archived = await run_tool(ctx, "get_runbook", {"runbook": "checkout-high-error-rate"})
    invalid = await run_tool(ctx, "get_runbook", {"runbook": "../etc"})

    assert old.error == "checkout-high-error-rate v3 is not available; the current version is v1"
    assert not stolen.ok
    assert archived.error == "no active runbook 'checkout-high-error-rate'"
    assert (invalid.error or "").startswith("invalid arguments")
