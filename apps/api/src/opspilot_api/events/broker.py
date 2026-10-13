"""Wakes live streams when incident events are committed.

One LISTEN connection per API process receives PostgreSQL notifications
(sent by a trigger, only on commit) and wakes the matching subscribers.
Subscribers then read the events themselves by sequence, so a missed or
coalesced wake-up never loses data. After a reconnect every subscriber is
woken once to catch up on anything committed during the gap.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field

import psycopg
import structlog

LISTEN_STATEMENT = "LISTEN incident_events"  # literal: no SQL is ever composed here

logger = structlog.get_logger()


@dataclass(eq=False)
class Subscription:
    organization_id: uuid.UUID
    incident_id: uuid.UUID | None
    wake: asyncio.Event = field(default_factory=asyncio.Event)

    def matches(self, organization_id: str, incident_id: str) -> bool:
        return str(self.organization_id) == organization_id and (
            self.incident_id is None or str(self.incident_id) == incident_id
        )


class EventBroker:
    def __init__(self, database_url: str, *, max_backoff_seconds: float = 5.0) -> None:
        # SQLAlchemy URL → libpq URL
        self._dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._max_backoff = max_backoff_seconds
        self._subscriptions: set[Subscription] = set()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="incident-event-broker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def subscribe(self, organization_id: uuid.UUID, incident_id: uuid.UUID | None) -> Subscription:
        subscription = Subscription(organization_id, incident_id)
        self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscriptions.discard(subscription)

    def _wake_all(self) -> None:
        for subscription in self._subscriptions:
            subscription.wake.set()

    async def _run(self) -> None:
        backoff = 0.2
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    self._dsn, autocommit=True
                ) as conn:
                    await conn.execute(LISTEN_STATEMENT)
                    logger.info("event broker listening")
                    backoff = 0.2
                    self._wake_all()  # catch up on anything missed while disconnected
                    async for notification in conn.notifies():
                        self._dispatch(notification.payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("event broker disconnected", error_type=type(exc).__name__)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)

    def _dispatch(self, payload: str) -> None:
        try:
            data = json.loads(payload)
            organization_id, incident_id = data["organization_id"], data["incident_id"]
        except (ValueError, KeyError):
            logger.warning("malformed incident event notification")
            return
        for subscription in self._subscriptions:
            if subscription.matches(organization_id, incident_id):
                subscription.wake.set()
