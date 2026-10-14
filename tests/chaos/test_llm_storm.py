"""LLM timeouts and 5xx storms: retries stay bounded and the investigation ends partial."""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import pytest
import sqlalchemy as sa
from opspilot_api.agents.investigation import Investigator
from opspilot_api.agents.llm import OllamaLLM
from opspilot_api.agents.runner import InvestigationRunner, context_factory
from opspilot_api.db.models import AgentRun, Evidence, Investigation, InvestigationStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.integration.test_investigation import setup
from tests.integration.test_investigation_runner import Kube, Logs, Metrics, Traces

from chaos.harness import Controlled, FlakyModelServer

ATTEMPTS = 3


@pytest.fixture
async def sessions(postgres: Controlled) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(postgres.url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture(params=["503", "hang"])
def model_server(request: pytest.FixtureRequest) -> Iterator[FlakyModelServer]:
    server = FlakyModelServer(request.param, hang_seconds=3.0)
    yield server
    server.close()


def runner(sessions: async_sessionmaker[AsyncSession], llm: OllamaLLM) -> InvestigationRunner:
    make = context_factory(
        sessions,
        metrics=Metrics(),
        logs=Logs(),
        traces=Traces(),
        kube=Kube(),
        embedder=None,
        allowed_namespaces=frozenset({"demo"}),
    )
    return InvestigationRunner(sessions, lambda: Investigator(sessions, llm, make))


async def test_a_model_outage_gives_a_bounded_partial_investigation(
    sessions: async_sessionmaker[AsyncSession], model_server: FlakyModelServer
) -> None:
    investigation_id: uuid.UUID = await setup(sessions)
    llm = OllamaLLM(
        model_server.url, "qwen2.5:7b-instruct", timeout=0.5, attempts=ATTEMPTS, backoff=0.05
    )
    started = time.monotonic()
    try:
        assert await runner(sessions, llm).run_once() is True
    finally:
        await llm.aclose()
    took = time.monotonic() - started

    async with sessions() as session:
        done = await session.get_one(Investigation, investigation_id)
        runs = list(
            await session.scalars(
                sa.select(AgentRun.status).where(AgentRun.investigation_id == investigation_id)
            )
        )
        evidence = await session.scalar(
            sa.select(sa.func.count()).where(Evidence.investigation_id == investigation_id)
        )
    assert done.status is InvestigationStatus.PARTIAL
    assert done.result is not None
    assert done.result["manual_review"] is True
    assert evidence, "tool evidence is kept even though the model never answered"
    assert runs
    assert set(runs) == {"fallback"}
    # Every model call was tried exactly ATTEMPTS times, never more.
    assert model_server.requests == ATTEMPTS * len(runs)
    assert took < 60


async def test_a_slow_model_does_not_let_a_second_worker_take_over(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Model calls that outlast the lease must not hand the job to another worker."""
    from opspilot_api.agents import runner as runner_module
    from opspilot_api.agents.llm import ScriptedLLM
    from tests.integration.test_investigation import happy_model

    monkeypatch.setattr(runner_module, "LEASE", timedelta(seconds=2))
    investigation_id: uuid.UUID = await setup(sessions)
    server = FlakyModelServer("hang", hang_seconds=2.0)
    # Each model call takes about 3 x 0.8 s, longer than the 2 s lease.
    slow = OllamaLLM(
        server.url, "qwen2.5:7b-instruct", timeout=0.8, attempts=ATTEMPTS, backoff=0.05
    )
    make = context_factory(
        sessions,
        metrics=Metrics(),
        logs=Logs(),
        traces=Traces(),
        kube=Kube(),
        embedder=None,
        allowed_namespaces=frozenset({"demo"}),
    )
    other = InvestigationRunner(
        sessions, lambda: Investigator(sessions, ScriptedLLM(happy_model()), make)
    )
    try:
        working = asyncio.create_task(runner(sessions, slow).run_once())
        await asyncio.sleep(0.2)  # let it claim first
        stolen = 0
        while not working.done():
            stolen += await other.run_once()
            await asyncio.sleep(0.3)
        await working
    finally:
        await slow.aclose()
        server.close()

    async with sessions() as session:
        done = await session.get_one(Investigation, investigation_id)
    assert stolen == 0, "a second worker took over a job that was still running"
    assert done.attempts == 1
