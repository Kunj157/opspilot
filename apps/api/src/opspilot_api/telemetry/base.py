import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

import httpx


class TelemetryUnavailable(Exception):
    """An observability backend could not answer; the message never includes its body."""


def label_value(value: str) -> str:
    """A quoted PromQL/LogQL label value, safe for any input."""
    return json.dumps(value)


@dataclass(frozen=True)
class Sample:
    labels: dict[str, str]
    value: float


@dataclass(frozen=True)
class Point:
    at: datetime
    value: float


@dataclass(frozen=True)
class Series:
    labels: dict[str, str]
    points: list[Point]


@dataclass(frozen=True)
class LogLine:
    at: datetime
    line: str
    labels: dict[str, str]


@dataclass(frozen=True)
class TraceSummary:
    trace_id: str
    root_service: str | None
    root_name: str | None
    started_at: datetime | None
    duration_ms: float | None


@dataclass(frozen=True)
class Span:
    service: str
    name: str
    kind: str
    duration_ms: float
    error: bool
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceDetail:
    trace_id: str
    spans: list[Span]


class MetricsProvider(Protocol):
    async def query(self, promql: str, at: datetime) -> list[Sample]: ...

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: timedelta
    ) -> list[Series]: ...


class LogsProvider(Protocol):
    async def search(
        self, logql: str, start: datetime, end: datetime, limit: int
    ) -> list[LogLine]: ...


class TracesProvider(Protocol):
    async def search(
        self, service: str, start: datetime, end: datetime, limit: int
    ) -> list[TraceSummary]: ...

    async def get(self, trace_id: str) -> TraceDetail | None: ...


class Backend:
    """Shared HTTP plumbing: one client, a timeout, and uniform failures."""

    name = "telemetry"

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self.client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise TelemetryUnavailable(f"{self.name} unreachable: {type(exc).__name__}") from exc
        if response.status_code == 404:
            return None
        if response.is_error:
            raise TelemetryUnavailable(f"{self.name} returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise TelemetryUnavailable(f"{self.name} returned invalid JSON") from exc

    async def aclose(self) -> None:
        await self.client.aclose()
