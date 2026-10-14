"""Structured JSON logging.

Every entry carries timestamp, level, service, environment, and message;
request-scoped fields (request_id, trace_id, span_id, user_id, organization_id)
are bound through structlog context variables.
"""

import logging
import sys

import structlog
from structlog.typing import EventDict, WrappedLogger

from opspilot_api.config import Settings
from opspilot_api.redaction import redact


def configure_logging(settings: Settings) -> None:
    static_fields = {"service": settings.service_name, "environment": settings.app_env}

    def add_static_fields(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        for key, value in static_fields.items():
            event_dict.setdefault(key, value)
        return event_dict

    def redact_secrets(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        redacted: EventDict = redact(event_dict)
        return redacted

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            add_static_fields,
            structlog.processors.format_exc_info,
            structlog.processors.EventRenamer("message"),
            redact_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=False,
    )
