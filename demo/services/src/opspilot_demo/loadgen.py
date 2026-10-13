"""Steady synthetic shoppers: mostly browsing, some checkouts."""

import asyncio
import logging
import random
from dataclasses import dataclass

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("opspilot_demo.loadgen")


class LoadSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOAD_", frozen=True)

    target_url: str = "http://storefront"
    rps: float = Field(default=5.0, gt=0, le=200)
    checkout_ratio: float = Field(default=0.3, ge=0, le=1)
    timeout_seconds: float = Field(default=5.0, gt=0)


@dataclass
class Stats:
    sent: int = 0
    failed: int = 0


async def _one(client: httpx.AsyncClient, checkout: bool, stats: Stats) -> None:
    try:
        if checkout:
            response = await client.post(
                "/api/checkout", json={"items": [{"sku": "mug", "quantity": 1}]}
            )
        else:
            response = await client.get("/api/products")
        failed = response.is_error
    except httpx.HTTPError:
        failed = True
    stats.sent += 1
    stats.failed += failed


async def run(
    settings: LoadSettings,
    *,
    requests: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    seed: int | None = None,
) -> Stats:
    """Send requests at `settings.rps` until `requests` are done (forever when None)."""
    chance = random.Random(seed)  # noqa: S311 - traffic mix, not security
    stats = Stats()
    pending: set[asyncio.Task[None]] = set()
    async with httpx.AsyncClient(
        base_url=settings.target_url, transport=transport, timeout=settings.timeout_seconds
    ) as client:
        issued = 0
        while requests is None or issued < requests:
            task = asyncio.create_task(
                _one(client, chance.random() < settings.checkout_ratio, stats)
            )
            pending.add(task)
            task.add_done_callback(pending.discard)
            issued += 1
            if issued % 100 == 0:
                logger.info("load progress", extra={"sent": stats.sent, "failed": stats.failed})
            await asyncio.sleep(1 / settings.rps)
        await asyncio.gather(*pending)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(LoadSettings()))
