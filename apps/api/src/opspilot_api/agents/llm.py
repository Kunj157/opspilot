"""Provider-neutral LLM gateway for the investigation agents.

Agents only ever ask for one thing: a JSON object matching a pydantic
schema. Every provider gets the same treatment - prompts are redacted,
output is validated (with one repair attempt), transient failures are
retried with backoff, and usage is accounted.

Providers: local Ollama (default; nothing leaves the machine), Anthropic
(when an API key is configured), and a scripted provider for tests.
"""

import asyncio
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic
import httpx
import httpx2
from pydantic import BaseModel, ValidationError

from opspilot_api.redaction import redact

# USD per million tokens (input, output). Local models cost nothing per call.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(pass(?:word|wd)?|secret|token|api[_-]?key|access[_-]?key|credentials?)(\s*[:=]\s*)(\S+)"
)
_SECRET_LITERALS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


class LLMError(Exception):
    """The model could not produce a valid answer; callers fall back deterministically."""


def redact_prompt(text: str) -> str:
    text = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    for pattern in _SECRET_LITERALS:
        text = pattern.sub("[REDACTED]", text)
    redacted: str = redact(text)
    return redacted


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.latency_ms += other.latency_ms
        self.cost_usd += other.cost_usd


@dataclass
class Completion[T: BaseModel]:
    value: T
    usage: Usage = field(default_factory=Usage)


@dataclass
class Raw:
    """One provider response before validation."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLM(Protocol):
    provider: str
    model: str

    async def complete_json[T: BaseModel](
        self, system: str, prompt: str, schema: type[T]
    ) -> Completion[T]: ...


def _strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with additionalProperties: false everywhere (structured-output rules)."""

    def close(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: close(v) for k, v in node.items()}
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
            return node
        if isinstance(node, list):
            return [close(v) for v in node]
        return node

    result: dict[str, Any] = close(schema.model_json_schema())
    return result


class _Base:
    provider = "base"
    model = ""

    def __init__(self, *, attempts: int = 3, backoff: float = 1.0) -> None:
        self.attempts = attempts
        self.backoff = backoff

    async def _call(self, system: str, prompt: str, schema: dict[str, Any]) -> Raw:
        raise NotImplementedError

    def _cost(self, raw: Raw) -> float:
        price_in, price_out = PRICES.get(self.model, (0.0, 0.0))
        return (raw.input_tokens * price_in + raw.output_tokens * price_out) / 1_000_000

    async def _with_retries(self, system: str, prompt: str, schema: dict[str, Any]) -> Raw:
        for attempt in range(self.attempts):
            try:
                return await self._call(system, prompt, schema)
            except _TransientError as exc:
                if attempt == self.attempts - 1:
                    raise LLMError(f"{self.provider} unavailable: {exc}") from exc
                await asyncio.sleep(self.backoff * 2**attempt)
        raise AssertionError("unreachable")

    async def complete_json[T: BaseModel](
        self, system: str, prompt: str, schema: type[T]
    ) -> Completion[T]:
        usage = Usage()
        system, prompt = redact_prompt(system), redact_prompt(prompt)
        json_schema = _strict_schema(schema)
        for attempt in range(2):
            started = time.perf_counter()
            raw = await self._with_retries(system, prompt, json_schema)
            usage.add(
                Usage(
                    calls=1,
                    input_tokens=raw.input_tokens,
                    output_tokens=raw.output_tokens,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    cost_usd=self._cost(raw),
                )
            )
            try:
                return Completion(schema.model_validate_json(raw.text), usage)
            except ValidationError as exc:
                if attempt == 1:
                    raise LLMError(
                        f"output did not match the schema: {exc.error_count()} errors"
                    ) from exc
                prompt = (
                    f"{prompt}\n\nYour previous answer was invalid ({exc.error_count()} schema "
                    "errors). Reply with one JSON object that matches the schema exactly."
                )
        raise AssertionError("unreachable")


class _TransientError(Exception):
    """Worth retrying: timeouts, connection failures, 429 and 5xx."""


class OllamaLLM(_Base):
    provider = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.model = model
        # Accept the OpenAI-style ".../v1" base URL too; the native API lives at the root.
        self.client = httpx.AsyncClient(
            base_url=base_url.removesuffix("/").removesuffix("/v1"),
            timeout=timeout,
            transport=transport,
        )

    async def _call(self, system: str, prompt: str, schema: dict[str, Any]) -> Raw:
        try:
            response = await self.client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "format": schema,
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
        except httpx.HTTPError as exc:
            raise _TransientError(type(exc).__name__) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise _TransientError(f"HTTP {response.status_code}")
        if response.is_error:
            raise LLMError(f"ollama rejected the request: HTTP {response.status_code}")
        body = response.json()
        return Raw(
            text=body.get("message", {}).get("content", ""),
            input_tokens=int(body.get("prompt_eval_count", 0)),
            output_tokens=int(body.get("eval_count", 0)),
        )


class AnthropicLLM(_Base):
    provider = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-5-5",
        *,
        timeout: float = 120.0,
        transport: httpx2.AsyncBaseTransport | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.model = model
        http_client = httpx2.AsyncClient(transport=transport) if transport else None
        # Retries are ours (same policy for every provider), so the SDK's are off.
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=0, http_client=http_client
        )

    async def _call(self, system: str, prompt: str, schema: dict[str, Any]) -> Raw:
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=8000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except (
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APIConnectionError,
        ) as exc:
            raise _TransientError(type(exc).__name__) from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"anthropic rejected the request: HTTP {exc.status_code}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("the model refused this request")
        text = next((b.text for b in response.content if b.type == "text"), "")
        return Raw(text, response.usage.input_tokens, response.usage.output_tokens)


class ScriptedLLM:
    """Deterministic answers for tests and evals: a list, or a function of (schema, prompt)."""

    provider = "scripted"
    model = "scripted"

    def __init__(
        self, script: list[dict[str, Any]] | Callable[[type[BaseModel], str], dict[str, Any]]
    ) -> None:
        self.script = script
        self.prompts: list[tuple[str, str]] = []

    async def complete_json[T: BaseModel](
        self, system: str, prompt: str, schema: type[T]
    ) -> Completion[T]:
        usage = Usage()
        for attempt in range(2):
            self.prompts.append((system, prompt))
            if callable(self.script):
                answer = self.script(schema, prompt)
            else:
                if not self.script:
                    raise LLMError("scripted model has no more answers")
                answer = self.script.pop(0)
            usage.add(Usage(calls=1))
            try:
                return Completion(schema.model_validate(answer), usage)
            except ValidationError as exc:
                if attempt == 1:
                    raise LLMError("output did not match the schema") from exc
                prompt = f"{prompt}\n\nYour previous answer was invalid. Reply with valid JSON."
        raise AssertionError("unreachable")


def build_llm(provider: str, model: str, base_url: str | None, api_key: str | None) -> LLM:
    if provider == "anthropic":
        if not api_key:
            raise ValueError("LLM_PROVIDER=anthropic needs LLM_API_KEY")
        return AnthropicLLM(api_key, model)
    if provider == "ollama":
        return OllamaLLM(base_url or "http://localhost:11434", model)
    raise ValueError(f"unknown LLM provider {provider!r}")


def as_json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)
