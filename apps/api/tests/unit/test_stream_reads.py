"""Live streams at the same position share one database read."""

import asyncio
import uuid
from typing import Any

import pytest

from opspilot_api.routes import incident_streams


class Principal:
    organization_id = uuid.uuid4()


async def test_concurrent_subscribers_share_one_read(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    async def events_after(factory: Any, principal: Any, incident_id: Any, after: int) -> list[Any]:
        calls.append(after)
        await asyncio.sleep(0.05)
        return []

    monkeypatch.setattr(incident_streams, "_events_after", events_after)
    principal = Principal()

    same = await asyncio.gather(
        *(incident_streams._frames_after(None, principal, None, 41) for _ in range(20))  # type: ignore[arg-type]
    )
    other = await incident_streams._frames_after(None, principal, None, 7)  # type: ignore[arg-type]

    assert same == [[]] * 20
    assert other == []
    assert calls == [41, 7]
    assert incident_streams._inflight == {}


async def test_a_cancelled_subscriber_does_not_cancel_the_shared_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def events_after(factory: Any, principal: Any, incident_id: Any, after: int) -> list[Any]:
        await asyncio.sleep(0.05)
        return []

    monkeypatch.setattr(incident_streams, "_events_after", events_after)
    principal = Principal()
    leaving = asyncio.ensure_future(incident_streams._frames_after(None, principal, None, 3))  # type: ignore[arg-type]
    staying = asyncio.ensure_future(incident_streams._frames_after(None, principal, None, 3))  # type: ignore[arg-type]
    await asyncio.sleep(0.01)
    leaving.cancel()

    assert await staying == []
