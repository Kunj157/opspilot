"""Loads the runbooks in docs/runbooks into OpsPilot through the public API.

    uv run python -m opspilot_api.runbook_seed --api-url URL --token TOKEN [--dir PATH]

Each file's name is its slug; existing runbooks are updated only when the
text changed.
"""

import argparse
import asyncio
from pathlib import Path

import httpx

SOURCE = "https://github.com/Kunj157/opspilot/blob/main/docs/runbooks"


def _documents(directory: Path) -> list[tuple[str, str, str]]:
    """(slug, file name, content) for every runbook file in the directory."""
    return [
        (path.stem, path.name, path.read_text())
        for path in sorted(directory.glob("*.md"))
        if path.name != "README.md"
    ]


async def seed_runbooks(client: httpx.AsyncClient, directory: Path) -> dict[str, int]:
    documents = await asyncio.to_thread(_documents, directory)
    existing = {
        r["slug"]: r
        for r in (await client.get("/api/v1/runbooks", params={"status": "all"}))
        .raise_for_status()
        .json()["items"]
    }
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for slug, name, content in documents:
        body = {"content": content, "source_url": f"{SOURCE}/{name}"}
        if current := existing.get(slug):
            response = await client.put(f"/api/v1/runbooks/{current['id']}", json=body)
            changed = response.raise_for_status().json()["version"] != current["version"]
            counts["updated" if changed else "unchanged"] += 1
        else:
            (await client.post("/api/v1/runbooks", json={**body, "slug": slug})).raise_for_status()
            counts["created"] += 1
    return counts


async def _main(api_url: str, token: str, directory: Path) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=api_url, headers=headers, timeout=60) as client:
        counts = await seed_runbooks(client, directory)
    print(f"Runbooks: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument(
        "--dir", type=Path, default=Path(__file__).resolve().parents[4] / "docs" / "runbooks"
    )
    args = parser.parse_args()
    asyncio.run(_main(args.api_url, args.token, args.dir))
