import asyncio
import contextvars
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from opspilot_demo.app import create_app
from opspilot_demo.settings import ServiceName, Settings

SERVICES: list[ServiceName] = ["storefront", "checkout", "payment", "inventory", "notification"]

Shop = Callable[..., httpx.AsyncClient]


@pytest.fixture
def spans() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
async def shop(spans: InMemorySpanExporter) -> AsyncIterator[Shop]:
    """Builds the whole shop in-process; services call each other over ASGI transports."""
    clients: list[httpx.AsyncClient] = []

    def build(**overrides: Settings) -> httpx.AsyncClient:
        apps: dict[str, object] = {}
        transports: dict[str, httpx.AsyncBaseTransport] = {}

        class Router(httpx.AsyncBaseTransport):
            """Separate services share no in-process context: only headers carry the trace."""

            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                target = transports[request.url.host]
                return await asyncio.create_task(
                    target.handle_async_request(request), context=contextvars.Context()
                )

        for name in SERVICES:
            settings = overrides.get(name) or Settings(service_name=name)
            apps[name] = create_app(settings, span_exporter=spans, transport=Router())
            transports[name] = httpx.ASGITransport(app=apps[name])  # type: ignore[arg-type]
        client = httpx.AsyncClient(transport=transports["storefront"], base_url="http://storefront")
        clients.append(client)
        return client

    yield build
    for client in clients:
        await client.aclose()
