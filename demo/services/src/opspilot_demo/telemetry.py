"""Traces, metrics, and logs for every demo service, correlated by trace ID."""

import json
import logging
from datetime import UTC, datetime

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from prometheus_client import CollectorRegistry, Counter, Histogram

from opspilot_demo.settings import Settings


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


class Metrics:
    """The plan's required HTTP metrics, in a registry owned by one app."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
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


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True
