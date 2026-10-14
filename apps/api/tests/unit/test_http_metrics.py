"""Request metrics: counted per route template and status, exposed at /metrics."""

import httpx
import pytest
from fastapi import FastAPI

from opspilot_api.http_metrics import MetricsMiddleware, metrics

app = FastAPI()
app.add_middleware(MetricsMiddleware)
app.add_route("/metrics", metrics)


@app.get("/things/{thing_id}")
async def thing(thing_id: int) -> dict[str, int]:
    if thing_id == 0:
        raise RuntimeError("boom")
    return {"id": thing_id}


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_requests_are_counted_by_route_template_and_status(client: httpx.AsyncClient) -> None:
    for thing_id in (1, 2, 0):
        await client.get(f"/things/{thing_id}")

    body = (await client.get("/metrics")).text

    labels = 'method="GET",route="/things/{thing_id}",service="opspilot-api"'
    assert f'http_requests_total{{{labels},status="200"}} 2.0' in body
    assert (
        'http_errors_total{method="GET",route="/things/{thing_id}",service="opspilot-api"} 1.0'
        in body
    )
    assert "http_request_duration_seconds_bucket" in body
    assert "/things/1" not in body, "raw paths would explode cardinality"
