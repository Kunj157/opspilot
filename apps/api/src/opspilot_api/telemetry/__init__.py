"""Read-only adapters over the observability backends.

Callers depend on the protocols, so the detector, agents, and tests can use
fakes. Every upstream failure surfaces as TelemetryUnavailable.
"""

from opspilot_api.telemetry.base import (
    LogLine,
    LogsProvider,
    MetricsProvider,
    Point,
    Sample,
    Series,
    Span,
    TelemetryUnavailable,
    TraceDetail,
    TracesProvider,
    TraceSummary,
    label_value,
)
from opspilot_api.telemetry.loki import LokiLogs
from opspilot_api.telemetry.prometheus import PrometheusMetrics
from opspilot_api.telemetry.tempo import TempoTraces

__all__ = [
    "LogLine",
    "LogsProvider",
    "LokiLogs",
    "MetricsProvider",
    "Point",
    "PrometheusMetrics",
    "Sample",
    "Series",
    "Span",
    "TelemetryUnavailable",
    "TempoTraces",
    "TraceDetail",
    "TraceSummary",
    "TracesProvider",
    "label_value",
]
