"""The LLM gateway: structured output, repair, retries, redaction, usage, providers."""

import json
from typing import Any

import httpx
import httpx2
import pytest
from pydantic import BaseModel

from opspilot_api.agents.llm import (
    AnthropicLLM,
    LLMError,
    OllamaLLM,
    ScriptedLLM,
    redact_prompt,
)


class Finding(BaseModel):
    summary: str
    confidence: float


def test_prompts_are_redacted_before_they_leave() -> None:
    text = redact_prompt(
        "token=abc123 password: hunter2 Authorization: Bearer eyJa.b.c "
        "key sk-ant-REDACTME0123456789abcd and AKIAABCDEFGHIJKLMNOP"
    )

    for secret in ("abc123", "hunter2", "eyJa.b.c", "sk-ant-REDACTME", "AKIAABCDEFGHIJKLMNOP"):
        assert secret not in text
    assert "token=[REDACTED]" in text


async def test_scripted_llm_validates_and_counts_usage() -> None:
    llm = ScriptedLLM([{"summary": "checkout broke", "confidence": 0.9}])

    result = await llm.complete_json("system", "prompt", Finding)

    assert result.value == Finding(summary="checkout broke", confidence=0.9)
    assert result.usage.calls == 1
    assert llm.prompts[0][1] == "prompt"


async def test_invalid_output_is_repaired_once_then_fails() -> None:
    repaired = ScriptedLLM([{"summary": "x"}, {"summary": "x", "confidence": 0.5}])
    broken = ScriptedLLM([{"nope": 1}, {"nope": 2}])

    result = await repaired.complete_json("s", "p", Finding)
    assert result.value.confidence == 0.5
    assert "invalid" in repaired.prompts[1][1].lower()
    with pytest.raises(LLMError, match="schema"):
        await broken.complete_json("s", "p", Finding)


def ollama(handler: Any) -> OllamaLLM:
    return OllamaLLM(
        "http://ollama:11434",
        "qwen2.5:7b-instruct",
        transport=httpx.MockTransport(handler),
        backoff=0,
    )


async def test_ollama_sends_the_schema_and_reads_usage() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": '{"summary": "ok", "confidence": 0.7}'},
                "prompt_eval_count": 120,
                "eval_count": 30,
            },
        )

    result = await ollama(handler).complete_json("sys", "user token=s3cret", Finding)

    assert result.value.summary == "ok"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)
    body = seen[0]
    assert body["format"]["properties"]["confidence"]["type"] == "number"
    assert body["stream"] is False
    assert "s3cret" not in json.dumps(body["messages"])


async def test_transient_failures_are_retried_then_reported() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(
            200, json={"message": {"content": '{"summary": "s", "confidence": 1}'}}
        )

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert (await ollama(flaky).complete_json("s", "p", Finding)).value.summary == "s"
    with pytest.raises(LLMError, match="unavailable"):
        await ollama(down).complete_json("s", "p", Finding)


async def test_client_errors_are_not_retried() -> None:
    calls = {"n": 0}

    def bad(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad"})

    with pytest.raises(LLMError):
        await ollama(bad).complete_json("s", "p", Finding)
    assert calls["n"] == 1


async def test_anthropic_uses_structured_output_and_reports_cost() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [{"type": "text", "text": '{"summary": "a", "confidence": 0.8}'}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1000, "output_tokens": 200},
            },
        )

    llm = AnthropicLLM("test-key", "claude-opus-5-5", transport=httpx2.MockTransport(handler))
    result = await llm.complete_json("sys", "prompt", Finding)

    assert result.value.summary == "a"
    body = seen[0]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert body["system"] == "sys"
    assert result.usage.cost_usd == pytest.approx(1000 * 4e-6 + 200 * 20e-6)


async def test_anthropic_refusals_are_errors() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [],
                "stop_reason": "refusal",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 0},
            },
        )

    llm = AnthropicLLM("k", "claude-opus-5-5", transport=httpx2.MockTransport(handler))
    with pytest.raises(LLMError, match="refus"):
        await llm.complete_json("s", "p", Finding)
