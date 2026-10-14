"""Runbook ingestion: sanitize → split by section → embed → store, per version."""

import re
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.db.models import Runbook, RunbookChunk
from opspilot_api.runbooks.document import RunbookDocument, parse
from opspilot_api.runbooks.embeddings import Embedder, embed
from opspilot_api.runbooks.retrieval import looks_like_injection

MAX_CHUNK_CHARS = 1200


@dataclass(frozen=True)
class Chunk:
    heading: str
    content: str
    # What gets embedded: the runbook title gives every section its context.
    text: str


def sanitize(text: str) -> str:
    text = re.sub(r"<[^>]{0,200}>", "", text)
    text = re.sub(r"[^\S\n\t ]|[\x00-\x08\x0b-\x1f\x7f]", "", text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split(body: str) -> list[str]:
    parts: list[str] = []
    current = ""
    for paragraph in body.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            parts.append(current)
        # A single oversized paragraph is cut hard rather than dropped.
        while len(paragraph) > MAX_CHUNK_CHARS:
            parts.append(paragraph[:MAX_CHUNK_CHARS])
            paragraph = paragraph[MAX_CHUNK_CHARS:]
        current = paragraph
    if current:
        parts.append(current)
    return parts


def chunk(doc: RunbookDocument) -> list[Chunk]:
    chunks = []
    for section in doc.sections:
        parts = _split(sanitize(section.body))
        for i, part in enumerate(parts, 1):
            heading = section.heading if i == 1 else f"{section.heading} (part {i})"
            chunks.append(Chunk(heading[:200], part, f"{doc.title} — {heading}\n{part}"))
    return chunks


async def ingest(session: AsyncSession, runbook: Runbook, embedder: Embedder) -> int:
    """Replace the runbook's chunks with freshly embedded ones for its current version."""
    chunks = chunk(parse(runbook.content))
    vectors = await embed(embedder, [c.text for c in chunks]) if chunks else []
    await session.execute(delete(RunbookChunk).where(RunbookChunk.runbook_id == runbook.id))
    session.add_all(
        RunbookChunk(
            runbook_id=runbook.id,
            organization_id=runbook.organization_id,
            version=runbook.version,
            ordinal=i,
            heading=c.heading,
            content=c.content,
            embedding=vector,
            flagged=looks_like_injection(c.content),
        )
        for i, (c, vector) in enumerate(zip(chunks, vectors, strict=True))
    )
    await session.flush()
    return len(chunks)
