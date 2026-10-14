import re
from datetime import UTC, datetime
from typing import Any

from opspilot_api.telemetry.base import Backend, Span, TraceDetail, TraceSummary, label_value

# Trace IDs reach this adapter from telemetry data and model output: only a
# hex ID may become part of the request path (no "../", "?", or "/").
_TRACE_ID = re.compile(r"^[0-9a-fA-F]{1,32}$")


def _attributes(raw: list[dict[str, Any]]) -> dict[str, str]:
    values = {}
    for item in raw:
        value = item.get("value", {})
        scalar = next(iter(value.values()), None) if value else None
        if scalar is not None:
            values[item["key"]] = str(scalar)
    return values


class TempoTraces(Backend):
    name = "tempo"

    async def search(
        self, service: str, start: datetime, end: datetime, limit: int, *, errors_only: bool = False
    ) -> list[TraceSummary]:
        condition = f"resource.service.name = {label_value(service)}"
        if errors_only:
            condition += " && status = error"
        body = await self.get_json(
            "/api/search",
            {
                "q": f"{{ {condition} }}",
                "start": int(start.timestamp()),
                "end": int(end.timestamp()),
                "limit": limit,
            },
        )
        return [
            TraceSummary(
                trace_id=t["traceID"],
                root_service=t.get("rootServiceName"),
                root_name=t.get("rootTraceName"),
                started_at=datetime.fromtimestamp(int(t["startTimeUnixNano"]) / 1e9, UTC)
                if t.get("startTimeUnixNano")
                else None,
                duration_ms=t.get("durationMs"),
            )
            for t in (body or {}).get("traces", [])
        ]

    async def get(self, trace_id: str) -> TraceDetail | None:
        if not _TRACE_ID.fullmatch(trace_id):
            return None
        body = await self.get_json(f"/api/traces/{trace_id}")
        if not body:
            return None
        spans = []
        for batch in body.get("batches", []):
            service = _attributes(batch["resource"]["attributes"]).get("service.name", "unknown")
            for scope in batch.get("scopeSpans", []):
                for raw in scope.get("spans", []):
                    spans.append(
                        Span(
                            service=service,
                            name=raw["name"],
                            kind=raw.get("kind", "SPAN_KIND_UNSPECIFIED"),
                            duration_ms=(
                                int(raw["endTimeUnixNano"]) - int(raw["startTimeUnixNano"])
                            )
                            / 1e6,
                            error=raw.get("status", {}).get("code") == "STATUS_CODE_ERROR",
                            attributes=_attributes(raw.get("attributes", [])),
                        )
                    )
        return TraceDetail(trace_id, spans)
