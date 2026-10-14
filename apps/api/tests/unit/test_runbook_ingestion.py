"""Sanitizing, chunking, and the deterministic embedder."""

import math

from opspilot_api.runbooks.document import parse
from opspilot_api.runbooks.embeddings import HashingEmbedder
from opspilot_api.runbooks.ingest import MAX_CHUNK_CHARS, chunk, sanitize

DOC = """---
title: Payment timeout
services: [payment]
version: 1
---

# Payment timeout

## Symptoms

Checkout fails with 502.

## Safe actions

Roll back payment.
"""


def test_sanitize_strips_markup_and_control_characters() -> None:
    dirty = "Restart <script>alert(1)</script>now\x00\x07\n\n\n\nThen  verify.  \n"

    assert sanitize(dirty) == "Restart alert(1)now\n\nThen  verify."


def test_chunks_follow_sections_and_carry_the_title() -> None:
    chunks = chunk(parse(DOC))

    assert [c.heading for c in chunks] == ["Symptoms", "Safe actions"]
    assert chunks[0].text.startswith("Payment timeout — Symptoms\n")
    assert chunks[1].content == "Roll back payment."


def test_long_sections_are_split_on_paragraphs() -> None:
    paragraphs = "\n\n".join(f"Step {i}: " + "word " * 60 for i in range(20))
    doc = parse(DOC.replace("Roll back payment.", paragraphs))

    parts = [c for c in chunk(doc) if c.heading.startswith("Safe actions")]

    assert len(parts) > 1
    assert all(len(p.content) <= MAX_CHUNK_CHARS for p in parts)
    assert parts[1].heading == "Safe actions (part 2)"


def test_hashing_embedder_is_deterministic_normalised_and_similarity_aware() -> None:
    embedder = HashingEmbedder()
    a, b, c = embedder.embed(
        [
            "checkout errors after release",
            "checkout errors after a release",
            "memory leak in notification",
        ]
    )

    assert len(a) == embedder.dimensions == 384
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    assert embedder.embed(["checkout errors after release"])[0] == a

    def cos(x: list[float], y: list[float]) -> float:
        return sum(p * q for p, q in zip(x, y, strict=True))

    assert cos(a, b) > cos(a, c)
