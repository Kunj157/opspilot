import math
from datetime import UTC, datetime, timedelta
from typing import Any

from opspilot_api.telemetry.base import Backend, Point, Sample, Series, TelemetryUnavailable


class PrometheusMetrics(Backend):
    name = "prometheus"

    async def _data(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        body = await self.get_json(path, params)
        if not body or body.get("status") != "success":
            raise TelemetryUnavailable("prometheus query failed")
        result: list[dict[str, Any]] = body["data"]["result"]
        return result

    async def query(self, promql: str, at: datetime) -> list[Sample]:
        result = await self._data("/api/v1/query", {"query": promql, "time": str(at.timestamp())})
        return [
            Sample(r["metric"], value)
            for r in result
            if not math.isnan(value := float(r["value"][1]))
        ]

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: timedelta
    ) -> list[Series]:
        result = await self._data(
            "/api/v1/query_range",
            {
                "query": promql,
                "start": str(start.timestamp()),
                "end": str(end.timestamp()),
                "step": f"{step.total_seconds():g}s",
            },
        )
        return [
            Series(
                r["metric"],
                [
                    Point(datetime.fromtimestamp(float(t), UTC), value)
                    for t, v in r["values"]
                    if not math.isnan(value := float(v))
                ],
            )
            for r in result
        ]
