from datetime import UTC, datetime

from opspilot_api.telemetry.base import Backend, LogLine


class LokiLogs(Backend):
    name = "loki"

    async def search(self, logql: str, start: datetime, end: datetime, limit: int) -> list[LogLine]:
        body = await self.get_json(
            "/loki/api/v1/query_range",
            {
                "query": logql,
                "start": str(int(start.timestamp() * 1e9)),
                "end": str(int(end.timestamp() * 1e9)),
                "limit": limit,
                "direction": "backward",
            },
        )
        lines = [
            LogLine(datetime.fromtimestamp(int(ns) / 1e9, UTC), line, stream["stream"])
            for stream in (body or {}).get("data", {}).get("result", [])
            for ns, line in stream["values"]
        ]
        return sorted(lines, key=lambda line: line.at, reverse=True)[:limit]
