"""Remove secrets from data before it is logged or stored."""

import re
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|credential|private[_-]?key)",
    re.IGNORECASE,
)
_SENSITIVE_TEXT = [
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*"),
]


def _redact_text(text: str) -> str:
    for pattern in _SENSITIVE_TEXT:
        text = pattern.sub(REDACTED, text)
    return text


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if isinstance(key, str) and _SENSITIVE_KEY.search(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(redact(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value
