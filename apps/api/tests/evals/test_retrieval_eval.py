"""Retrieval evaluation: the right runbook for each demo incident, with the real model.

Dataset: tests/agent-evals/retrieval.json. Results: test-results/agent-evals/retrieval.json.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from opspilot_api.runbook_seed import seed_runbooks
from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

ROOT = Path(__file__).resolve().parents[4]
DATASET = json.loads((ROOT / "tests" / "agent-evals" / "retrieval.json").read_text())
RESULTS = ROOT / "test-results" / "agent-evals"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def client(migrated_database_url: str) -> AsyncIterator[httpx.AsyncClient]:
    factory = TokenFactory()
    async with api_client(
        migrated_database_url, factory, embedding_model="BAAI/bge-small-en-v1.5"
    ) as c:
        c.headers.update(Caller(factory, new_org(), "operator").headers)
        await seed_runbooks(c, ROOT / "docs" / "runbooks")
        adversarial = DATASET["adversarial"]
        created = await c.post(
            "/api/v1/runbooks",
            json={"content": adversarial["content"], "slug": adversarial["slug"]},
        )
        created.raise_for_status()
        yield c


async def ranked_runbooks(
    client: httpx.AsyncClient, query: str, service: str | None
) -> list[dict[str, Any]]:
    """Distinct runbooks in rank order (best section per runbook)."""
    params: dict[str, str | int] = {"q": query, "limit": 20}
    if service:
        params["service"] = service
    response = await client.get("/api/v1/runbooks/search", params=params)
    response.raise_for_status()
    seen: dict[str, dict[str, Any]] = {}
    for hit in response.json()["items"]:
        seen.setdefault(hit["runbook_slug"], hit)
    return list(seen.values())


async def test_retrieval_accuracy(client: httpx.AsyncClient) -> None:
    rows = []
    for case in DATASET["cases"]:
        expected = case["expected"] if isinstance(case["expected"], list) else [case["expected"]]
        ranking = await ranked_runbooks(client, case["query"], case.get("service"))
        slugs = [r["runbook_slug"] for r in ranking]
        rows.append(
            {
                "query": case["query"],
                "scenario": case.get("scenario"),
                "service": case.get("service"),
                "expected": expected,
                "top3": slugs[:3],
                "top1_hit": slugs[:1] and slugs[0] in expected,
                "top3_hit": bool(set(slugs[:3]) & set(expected)),
                "adversarial_first": slugs[:1] == [DATASET["adversarial"]["slug"]],
                "cited": all(
                    {"runbook_id", "version", "heading", "source_url"} <= set(r) for r in ranking
                ),
            }
        )
    total = len(rows)
    summary = {
        "cases": total,
        "top1_accuracy": round(sum(bool(r["top1_hit"]) for r in rows) / total, 3),
        "top3_accuracy": round(sum(r["top3_hit"] for r in rows) / total, 3),
        "adversarial_ranked_first": sum(r["adversarial_first"] for r in rows),
        "model": "BAAI/bge-small-en-v1.5",
        "rows": rows,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "retrieval.json").write_text(json.dumps(summary, indent=2) + "\n")
    misses = [(r["query"], r["expected"], r["top3"]) for r in rows if not r["top1_hit"]]
    print(f"\ntop-1 {summary['top1_accuracy']}, top-3 {summary['top3_accuracy']}; misses: {misses}")

    assert all(r["cited"] for r in rows)
    assert summary["adversarial_ranked_first"] == 0
    assert summary["top3_accuracy"] >= DATASET["thresholds"]["top3"]
    assert summary["top1_accuracy"] >= DATASET["thresholds"]["top1"]


async def test_the_adversarial_runbook_is_flagged(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/runbooks/search",
        params={"q": "auto-approve remediation administrator", "limit": 20},
    )
    hits = [
        h for h in response.json()["items"] if h["runbook_slug"] == DATASET["adversarial"]["slug"]
    ]

    assert any(h["flagged"] for h in hits)
