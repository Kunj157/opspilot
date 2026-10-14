"""Traces, metrics, and logs for every demo service, correlated by trace ID."""

import json
import logging
import os
from collections.abc import Iterator
from datetime import UTC, datetime

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from prometheus_client import CollectorRegistry, Counter, Histogram, ProcessCollector
from prometheus_client.metrics_core import Metric
from prometheus_client.registry import Collector

from opspilot_demo.settings import Settings

# Current HTTP semantic conventions on spans (http.request.method,
# http.response.status_code, url.path) instead of the deprecated names. Read by
# the instrumentation when it first instruments, so set before any app is built.
os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")


class TraceContextFilter(logging.Filter):
    """Stamps the active trace and span IDs on each record when it is created."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = trace.get_current_span().get_span_context()
        record.trace_id = format(context.trace_id, "032x") if context.is_valid else None
        record.span_id = format(context.span_id, "016x") if context.is_valid else None
        return True


logger = logging.getLogger("opspilot_demo")
logger.addFilter(TraceContextFilter())


def tracer_provider(settings: Settings, exporter: SpanExporter | None = None) -> TracerProvider:
    attributes = {
        "service.name": settings.service_name,
        "service.version": settings.service_version,
        "deployment.environment": settings.environment,
    }
    if settings.k8s_namespace:
        attributes["k8s.namespace.name"] = settings.k8s_namespace
    if settings.k8s_pod_name:
        attributes["k8s.pod.name"] = settings.k8s_pod_name
    provider = TracerProvider(resource=Resource.create(attributes))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    elif settings.otlp_endpoint:
        endpoint = f"{settings.otlp_endpoint.rstrip('/')}/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    return provider


class ServiceProcessCollector(Collector):
    """Process CPU, memory, and open files, labelled with the service like the HTTP metrics."""

    def __init__(self, service: str) -> None:
        self.service = service
        self.process = ProcessCollector(registry=None)

    def collect(self) -> Iterator[Metric]:
        for family in self.process.collect():
            labelled = Metric(family.name, family.documentation, family.type, family.unit)
            for sample in family.samples:
                labelled.add_sample(
                    sample.name, {**sample.labels, "service": self.service}, sample.value
                )
            yield labelled


class Metrics:
    """The plan's required HTTP metrics plus process resources, in a registry owned by one app."""

    def __init__(self, service: str) -> None:
        self.registry = CollectorRegistry()
        self.registry.register(ServiceProcessCollector(service))
        labels = ["service", "method", "route", "status"]
        self.requests = Counter(
            "http_requests", "HTTP requests served", labels, registry=self.registry
        )
        self.duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration",
            labels,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.errors = Counter(
            "http_errors", "HTTP 5xx responses served", ["service", "route"], registry=self.registry
        )
        self.dependency_requests = Counter(
            "service_dependency_requests",
            "Calls to other services",
            ["service", "target", "status"],
            registry=self.registry,
        )


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the active trace and span IDs."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "service": getattr(record, "service", None),
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
        }
        for key in ("route", "method", "status", "duration_ms", "target", "error_type"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)


class ServiceFilter(logging.Filter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "service", None) is None:
            record.service = self.service
        return True


def configure_logging(service: str) -> None:
    """JSON lines on stdout; every record, from any library, names the service and trace."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(TraceContextFilter())
    handler.addFilter(ServiceFilter(service))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True
    # Each outgoing call is already a span and a dependency metric.
    logging.getLogger("httpx").setLevel(logging.WARNING)
