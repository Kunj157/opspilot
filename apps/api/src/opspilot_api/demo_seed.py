"""Registers the demo shop in the service catalog, through the public API.

    uv run python -m opspilot_api.demo_seed --api-url http://127.0.0.1:8000 --token "$TOKEN"

Idempotent: existing services are updated, dependencies are replaced.
"""

import argparse
import asyncio
from typing import Any

import httpx

OWNER = "shop-team"
REPOSITORY = "https://github.com/Kunj157/opspilot/tree/main/demo/services"

DEMO_SERVICES: list[dict[str, Any]] = [
    {"slug": "storefront", "name": "Storefront", "description": "Web front of the demo shop."},
    {"slug": "checkout", "name": "Checkout", "description": "Places orders."},
    {"slug": "payment", "name": "Payment", "description": "Charges orders."},
    {"slug": "inventory", "name": "Inventory", "description": "Stock levels and reservations."},
    {"slug": "notification", "name": "Notification", "description": "Order confirmations."},
]

DEMO_DEPENDENCIES: dict[str, list[str]] = {
    "storefront": ["checkout", "inventory"],
    "checkout": ["inventory", "payment", "notification"],
}


async def seed(client: httpx.AsyncClient) -> None:
    existing = {
        s["slug"]: s
        for s in (await client.get("/api/v1/services")).raise_for_status().json()["items"]
    }
    ids: dict[str, str] = {}
    for service in DEMO_SERVICES:
        fields = {
            **service,
            "owner_team": OWNER,
            "repository_url": REPOSITORY,
            "namespace": "demo",
            "deployment_name": service["slug"],
        }
        if service["slug"] in existing:
            current = existing[service["slug"]]
            response = await client.patch(f"/api/v1/services/{current['id']}", json=fields)
        else:
            response = await client.post("/api/v1/services", json=fields)
        ids[service["slug"]] = response.raise_for_status().json()["id"]
    for service in DEMO_SERVICES:
        targets = [ids[t] for t in DEMO_DEPENDENCIES.get(service["slug"], [])]
        (
            await client.put(
                f"/api/v1/services/{ids[service['slug']]}/dependencies",
                json={"target_ids": targets},
            )
        ).raise_for_status()


async def _main(api_url: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=api_url, headers=headers, timeout=10) as client:
        await seed(client)
    print(f"Seeded {len(DEMO_SERVICES)} demo services and their dependencies.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    asyncio.run(_main(args.api_url, args.token))
