"""Text embeddings for runbook retrieval.

The default is a small local ONNX model (no API key, no data leaves the
machine). The hashing embedder is deterministic and dependency-free, for
tests and offline use.
"""

import asyncio
import hashlib
import itertools
import math
import re
from pathlib import Path
from typing import Any, Protocol

from opspilot_api.db.models import EMBEDDING_DIMENSIONS

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class Embedder(Protocol):
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Signed feature hashing over words and word pairs, L2-normalised."""

    dimensions = EMBEDDING_DIMENSIONS

    def _vector(self, text: str) -> list[float]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        features = words + [f"{a} {b}" for a, b in itertools.pairwise(words)]
        vector = [0.0] * self.dimensions
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FastEmbedder:
    """bge-small via fastembed (ONNX). The model loads on first use."""

    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self, model: str = DEFAULT_MODEL, cache_dir: str | None = None) -> None:
        self.model_name = model
        self.cache_dir = cache_dir
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            # Imported lazily: loading onnxruntime is slow and tests never need it.
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self.model_name, cache_dir=self.cache_dir)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._load().embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self._load().query_embed([text])))]


def build_embedder(model: str, cache_dir: str | None) -> Embedder:
    if model == "hashing":
        return HashingEmbedder()
    return FastEmbedder(model, cache_dir or str(Path.home() / ".cache" / "opspilot" / "models"))


async def embed(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    """Embed off the event loop; model inference is CPU-bound."""
    return await asyncio.to_thread(embedder.embed, texts)


async def embed_query(embedder: Embedder, text: str) -> list[float]:
    return await asyncio.to_thread(embedder.embed_query, text)
