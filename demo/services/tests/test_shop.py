import json
import logging

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from opspilot_demo.settings import Settings
from tests.conftest import Shop


def metric(text: str, name: str, **labels: str) -> float:
    """Value of one Prometheus sample from the text exposition."""
    for line in text.splitlines():
        if not line.startswith(name + "{"):
            continue
        sample_labels = dict(
            part.split("=", 1) for part in line[len(name) + 1 : line.index("}")].split(",")
        )
        if all(sample_labels.get(k) == f'"{v}"' for k, v in labels.items()):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


async def test_checkout_flows_through_every_service_in_one_trace(
    shop: Shop, spans: InMemorySpanExporter
) -> None:
    client = shop()

    response = await client.post("/api/checkout", json={"items": [{"sku": "mug", "quantity": 2}]})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    server_spans = [s for s in spans.get_finished_spans() if s.kind.name == "SERVER"]
    assert {s.resource.attributes["service.name"] for s in server_spans} == {
        "storefront",
        "checkout",
        "payment",
        "inventory",
        "notification",
    }
    assert len({s.context.trace_id for s in spans.get_finished_spans()}) == 1


async def test_spans_carry_the_required_resource_attributes(
    shop: Shop, spans: InMemorySpanExporter
) -> None:
    await shop().get("/api/products")

    span = next(s for s in spans.get_finished_spans() if s.kind.name == "SERVER")
    for key in ("service.name", "service.version", "deployment.environment"):
        assert key in span.resource.attributes


async def test_requests_are_counted_and_timed(shop: Shop) -> None:
    client = shop()
    await client.get("/api/products")
    await client.get("/api/products")

    text = (await client.get("/metrics")).text

    labels = {"service": "storefront", "route": "/api/products", "method": "GET", "status": "200"}
    assert metric(text, "http_requests_total", **labels) == 2
    assert metric(text, "http_request_duration_seconds_count", **labels) == 2
    assert (
        metric(
            text,
            "service_dependency_requests_total",
            service="storefront",
            target="inventory",
            status="200",
        )
        == 2
    )


async def test_logs_carry_the_trace_id(shop: Shop, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="opspilot_demo")

    await shop().get("/api/products")

    from opspilot_demo.telemetry import JsonFormatter

    records = [json.loads(JsonFormatter().format(r)) for r in caplog.records]
    served = [r for r in records if r["message"] == "request served"]
    assert served
    assert all(len(r["trace_id"]) == 32 and r["service"] for r in served)


async def test_an_injected_error_rate_returns_500_and_marks_the_span(
    shop: Shop, spans: InMemorySpanExporter
) -> None:
    client = shop(checkout=Settings(service_name="checkout", fault_error_rate=1.0))

    response = await client.post("/api/checkout", json={"items": [{"sku": "mug", "quantity": 1}]})

    assert response.status_code == 502
    text = (await client.get("/metrics")).text
    assert (
        metric(
            text,
            "service_dependency_requests_total",
            service="storefront",
            target="checkout",
            status="500",
        )
        == 1
    )
    failed = [
        s
        for s in spans.get_finished_spans()
        if s.resource.attributes["service.name"] == "checkout" and s.kind.name == "SERVER"
    ]
    assert failed[0].status.status_code is StatusCode.ERROR
    assert failed[0].attributes is not None
    assert failed[0].attributes["error.type"] == "InjectedFault"


async def test_errors_are_counted(shop: Shop) -> None:
    client = shop(storefront=Settings(service_name="storefront", fault_error_rate=1.0))

    response = await client.get("/api/products")

    assert response.status_code == 500
    text = (await client.get("/metrics")).text
    assert metric(text, "http_errors_total", service="storefront", route="/api/products") == 1


async def test_injected_latency_is_added(shop: Shop) -> None:
    client = shop(inventory=Settings(service_name="inventory", fault_latency_ms=200))

    response = await client.get("/api/products")

    assert response.status_code == 200
    text = (await client.get("/metrics")).text
    total = metric(
        text,
        "http_request_duration_seconds_sum",
        service="storefront",
        route="/api/products",
        method="GET",
        status="200",
    )
    assert total >= 0.2


async def test_health_and_metrics_are_never_faulty(shop: Shop) -> None:
    client = shop(storefront=Settings(service_name="storefront", fault_error_rate=1.0))

    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/metrics")).status_code == 200


async def test_a_failed_notification_does_not_fail_the_order(shop: Shop) -> None:
    client = shop(notification=Settings(service_name="notification", fault_error_rate=1.0))

    response = await client.post("/api/checkout", json={"items": [{"sku": "mug", "quantity": 1}]})

    assert response.status_code == 200
    assert response.json()["notified"] is False


async def test_an_unreachable_dependency_is_a_502(spans: InMemorySpanExporter) -> None:
    from opspilot_demo.app import create_app

    class Down(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

    app = create_app(Settings(service_name="storefront"), span_exporter=spans, transport=Down())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://storefront"
    ) as client:
        response = await client.get("/api/products")

    assert response.status_code == 502
    assert response.json()["detail"] == "inventory unavailable"


def test_library_log_lines_name_the_service(capsys: pytest.CaptureFixture[str]) -> None:
    from opspilot_demo.telemetry import configure_logging

    configure_logging("payment")
    logging.getLogger("uvicorn.error").info("started")

    line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert (line["service"], line["message"], line["trace_id"]) == ("payment", "started", None)
    logging.getLogger().handlers.clear()


def test_unknown_service_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="service_name"):
        Settings(service_name="warehouse")  # type: ignore[arg-type]
