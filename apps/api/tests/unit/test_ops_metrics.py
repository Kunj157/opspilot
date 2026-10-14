"""Metrics behind the operational alerts: LLM spend, pool usage, recheck reasons."""

import json
from typing import Any

import httpx
import pytest
from prometheus_client import REGISTRY
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine

from opspilot_api.agents.llm import PRICES, LLMError, OllamaLLM
from opspilot_api.ops_metrics import POOLS, blocked_reason


class Answer(BaseModel):
    summary: str


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def ollama(handler: Any, model: str) -> OllamaLLM:
    return OllamaLLM(
        "http://ollama:11434", model, transport=httpx.MockTransport(handler), backoff=0
    )


async def test_llm_calls_count_tokens_cost_and_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(PRICES, "metered-model", (1.0, 2.0))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps({"summary": "ok"})},
                "prompt_eval_count": 1_000_000,
                "eval_count": 500_000,
            },
        )

    labels = {"provider": "ollama", "model": "metered-model"}
    before_cost = sample("opspilot_llm_cost_usd_total", **labels)
    before_ok = sample("opspilot_llm_requests_total", **labels, outcome="ok")

    await ollama(handler, "metered-model").complete_json("s", "p", Answer)

    assert sample("opspilot_llm_cost_usd_total", **labels) - before_cost == pytest.approx(2.0)
    assert sample("opspilot_llm_tokens_total", **labels, direction="output") >= 500_000
    assert sample("opspilot_llm_requests_total", **labels, outcome="ok") - before_ok == 1


async def test_failed_llm_calls_are_counted_as_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    labels = {"provider": "ollama", "model": "down-model", "outcome": "error"}
    before = sample("opspilot_llm_requests_total", **labels)

    with pytest.raises(LLMError):
        await ollama(handler, "down-model").complete_json("s", "p", Answer)

    assert sample("opspilot_llm_requests_total", **labels) - before == 1


async def test_pool_usage_is_read_at_scrape_time() -> None:
    engine = create_async_engine(
        "postgresql+psycopg://user@db.invalid/app", pool_size=4, max_overflow=6
    )
    POOLS.track("unit", engine)
    try:
        assert sample("opspilot_db_pool_connections_max", pool="unit") == 10
        assert sample("opspilot_db_pool_connections_in_use", pool="unit") == 0
    finally:
        POOLS.untrack("unit")
        await engine.dispose()
    assert REGISTRY.get_sample_value("opspilot_db_pool_connections_max", {"pool": "unit"}) is None


@pytest.mark.parametrize(
    ("problem", "reason"),
    [
        ("the proposal has no approval", "unapproved"),
        ("the proposal changed after it was approved", "stale_approval"),
        ("the proposal expired before it could run", "expired"),
        ("namespace 'kube-system' is not allowed", "namespace_not_allowed"),
        ("replicas must be between 1 and 10", "invalid_parameters"),
    ],
)
def test_recheck_problems_map_to_few_reasons(problem: str, reason: str) -> None:
    assert blocked_reason(problem) == reason
