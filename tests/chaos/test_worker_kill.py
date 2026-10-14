"""Worker killed mid-investigation: the lease expires, another worker resumes and finishes."""

import asyncio
import os
import signal
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from opspilot_api.db.models import (
    AgentRun,
    Evidence,
    IncidentEvent,
    Investigation,
    InvestigationStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.integration.test_investigation import setup
from tests.integration.test_investigation_runner import drain, happy_model, runner

from chaos.harness import Controlled


@pytest.fixture
async def sessions(postgres: Controlled) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(postgres.url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def investigation(
    sessions: async_sessionmaker[AsyncSession], id_: uuid.UUID
) -> Investigation:
    async with sessions() as session:
        return await session.get_one(Investigation, id_)


async def test_a_killed_workers_investigation_is_resumed_once(
    sessions: async_sessionmaker[AsyncSession], postgres: Controlled
) -> None:
    investigation_id = await setup(sessions)
    child = subprocess.Popen(  # noqa: S603, ASYNC220 - our interpreter; Popen does not block
        [sys.executable, str(Path(__file__).with_name("worker_child.py")), postgres.url],
        # cwd is apps/api (make test-chaos): the child imports the test helpers from there.
        env={**os.environ, "MODEL_DELAY": "1.0", "PYTHONPATH": os.getcwd()},
    )
    try:
        # Kill it once it has persisted a node past triage, mid-workflow.
        for _ in range(240):
            current = await investigation(sessions, investigation_id)
            if current.current_node not in (None, "triage"):
                break
            await asyncio.sleep(0.25)
        else:
            pytest.fail("the worker never got past triage")
        child.send_signal(signal.SIGKILL)
        child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()

    killed = await investigation(sessions, investigation_id)
    assert killed.status is InvestigationStatus.RUNNING
    assert killed.lease_until is not None
    assert killed.lease_until > datetime.now(UTC)
    resumed_from = killed.current_node

    # A live worker does not steal a leased job...
    second = runner(sessions, happy_model())
    assert await second.run_once() is False
    # ...until the lease runs out (fast-forwarded here instead of waiting ten minutes).
    async with sessions() as session:
        await session.execute(
            sa.update(Investigation)
            .where(Investigation.id == investigation_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    await drain(second)

    done = await investigation(sessions, investigation_id)
    assert done.status is InvestigationStatus.COMPLETED
    assert done.attempts == 2
    async with sessions() as session:
        finished = await session.scalar(
            sa.select(sa.func.count()).where(
                IncidentEvent.incident_id == done.incident_id,
                IncidentEvent.event_type == "incident.investigation_finished",
            )
        )
        evidence = [
            tuple(row)
            for row in await session.execute(
                sa.select(Evidence.evidence_type, Evidence.source, Evidence.summary).where(
                    Evidence.incident_id == done.incident_id
                )
            )
        ]
        runs = list(
            await session.scalars(
                sa.select(AgentRun.agent_name).where(AgentRun.investigation_id == investigation_id)
            )
        )
    assert finished == 1, "the investigation finished exactly once"
    assert len(evidence) == len(set(evidence)), (
        f"duplicate evidence after resuming at {resumed_from}"
    )
    assert runs.count("triage") == 1, "triage was not redone after the takeover"
