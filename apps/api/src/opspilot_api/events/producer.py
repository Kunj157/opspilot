"""Publishing to the event broker, behind a small interface tests can replace."""

from typing import Protocol

from aiokafka import AIOKafkaProducer
from opentelemetry import propagate


class Producer(Protocol):
    async def send(
        self, topic: str, key: bytes, value: bytes, headers: list[tuple[str, bytes]]
    ) -> None:
        """Return only once the broker has acknowledged the message."""
        ...


def trace_headers() -> list[tuple[str, bytes]]:
    """The current W3C trace context as message headers."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return [(k, v.encode()) for k, v in carrier.items()]


class KafkaProducer:
    """Idempotent producer: acks from all in-sync replicas, no duplicates on retry."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            enable_idempotence=True,
            acks="all",
            request_timeout_ms=10_000,
        )
        self._started = False

    async def send(
        self, topic: str, key: bytes, value: bytes, headers: list[tuple[str, bytes]]
    ) -> None:
        if not self._started:
            await self._producer.start()
            self._started = True
        await self._producer.send_and_wait(topic, value=value, key=key, headers=headers)

    async def aclose(self) -> None:
        if self._started:
            await self._producer.stop()
            self._started = False
