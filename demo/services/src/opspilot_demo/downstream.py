"""Calls from one demo service to another."""

from typing import Any

import httpx
from fastapi import HTTPException

from opspilot_demo.settings import Settings
from opspilot_demo.telemetry import Metrics, logger


class Downstream:
    """Calls to other services: traced, counted, and turned into 502s when they fail."""

    def __init__(self, settings: Settings, metrics: Metrics, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.metrics = metrics
        self.client = client

    async def call(self, target: str, method: str, path: str, **kwargs: Any) -> httpx.Response:
        base = getattr(self.settings, f"{target}_url")
        extra = {"service": self.settings.service_name, "target": target}
        try:
            response = await self.client.request(method, f"{base}{path}", **kwargs)
        except httpx.HTTPError as exc:
            self.metrics.dependency_requests.labels(
                self.settings.service_name, target, "error"
            ).inc()
            logger.warning(
                "dependency unavailable", extra={**extra, "error_type": type(exc).__name__}
            )
            raise HTTPException(502, f"{target} unavailable") from exc
        self.metrics.dependency_requests.labels(
            self.settings.service_name, target, str(response.status_code)
        ).inc()
        return response

    async def require(self, target: str, method: str, path: str, **kwargs: Any) -> Any:
        """Call and return the JSON body, or fail with 502 on any non-2xx."""
        response = await self.call(target, method, path, **kwargs)
        if response.is_error:
            raise HTTPException(502, f"{target} failed")
        return response.json()
