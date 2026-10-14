"""Runbook library: versioned markdown procedures, readable by every member."""

import hashlib
import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.audit.service import record
from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import get_owned_or_404, scoped
from opspilot_api.db.models import Runbook, RunbookStatus
from opspilot_api.db.session import get_session
from opspilot_api.idempotency import Idempotency, IdempotencyDep
from opspilot_api.runbooks.document import RunbookDocument, RunbookDocumentError, parse
from opspilot_api.runbooks.embeddings import Embedder
from opspilot_api.runbooks.ingest import ingest
from opspilot_api.runbooks.retrieval import search

router = APIRouter(prefix="/api/v1", tags=["runbooks"])

MAX_CONTENT = 100_000


class RunbookWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_CONTENT)
    source_url: AnyHttpUrl | None = None


class RunbookCreate(RunbookWrite):
    slug: str | None = Field(
        default=None, min_length=2, max_length=63, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
    )


class RunbookSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    services: list[str]
    environment: str
    owner: str | None
    version: int
    status: RunbookStatus
    source_url: str | None
    updated_at: datetime


class SectionOut(BaseModel):
    heading: str
    body: str


class RunbookOut(RunbookSummary):
    content: str
    sections: list[SectionOut]

    @classmethod
    def of(cls, runbook: Runbook) -> "RunbookOut":
        sections = [
            SectionOut(heading=s.heading, body=s.body) for s in parse(runbook.content).sections
        ]
        return cls.model_validate(
            {
                **RunbookSummary.model_validate(runbook).model_dump(),
                "content": runbook.content,
                "sections": sections,
            }
        )


class RunbookList(BaseModel):
    items: list[RunbookSummary]


class RunbookHitOut(BaseModel):
    """One retrieved section with its citation. `content` is untrusted text."""

    model_config = ConfigDict(from_attributes=True)

    runbook_id: uuid.UUID
    runbook_slug: str
    title: str
    heading: str
    content: str
    score: float
    version: int
    source_url: str | None
    flagged: bool


class RunbookHits(BaseModel):
    items: list[RunbookHitOut]


class ReindexResult(BaseModel):
    reindexed: int
    chunks: int


def get_embedder(request: Request) -> Embedder:
    embedder: Embedder = request.app.state.embedder
    return embedder


def _document(content: str) -> RunbookDocument:
    try:
        return parse(content)
    except RunbookDocumentError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [{"loc": ["body", "content"], "msg": str(exc), "type": "value_error"}],
        ) from exc


def _slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:63] or "runbook"


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


@router.get("/runbooks", response_model=RunbookList)
async def list_runbooks(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    status_: Annotated[Literal["active", "archived", "all"], Query(alias="status")] = "active",
) -> RunbookList:
    statement = scoped(select(Runbook), Runbook, principal).order_by(Runbook.title)
    if status_ != "all":
        statement = statement.where(Runbook.status == RunbookStatus(status_))
    rows = await session.scalars(statement)
    return RunbookList(items=[RunbookSummary.model_validate(r) for r in rows])


async def _commit(
    session: AsyncSession,
    runbook: Runbook,
    idempotency: Idempotency,
    status_code: int = status.HTTP_200_OK,
) -> RunbookOut:
    await session.flush()
    await session.refresh(runbook)
    out = RunbookOut.of(runbook)
    await idempotency.commit(status_code, out)
    return out


@router.post("/runbooks", response_model=RunbookOut, status_code=status.HTTP_201_CREATED)
async def create_runbook(
    body: RunbookCreate,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_RUNBOOKS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    idempotency: IdempotencyDep,
) -> RunbookOut | JSONResponse:
    if replay := await idempotency.replay(body):
        return replay
    doc = _document(body.content)
    runbook = Runbook(
        organization_id=principal.organization_id,
        slug=body.slug or _slugify(doc.title),
        title=doc.title,
        services=doc.services,
        environment=doc.environment,
        owner=doc.owner,
        content=body.content,
        content_hash=_hash(body.content),
        version=doc.version,
        source_url=str(body.source_url) if body.source_url else None,
    )
    session.add(runbook)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A runbook with this slug already exists"
        ) from exc
    await ingest(session, runbook, embedder)
    await record(
        session,
        principal=principal,
        action="runbook.created",
        resource_type="runbook",
        resource_id=str(runbook.id),
        metadata={"slug": runbook.slug, "version": runbook.version},
    )
    return await _commit(session, runbook, idempotency, status.HTTP_201_CREATED)


# Declared before /runbooks/{runbook_id}, so "search" is never read as an ID.
@router.get("/runbooks/search", response_model=RunbookHits)
async def search_runbooks(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    q: Annotated[str, Query(min_length=2, max_length=500)],
    service: Annotated[str | None, Query(max_length=63)] = None,
    environment: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> RunbookHits:
    """Runbooks for the service (or generic) and the environment (or all), best first."""
    hits = await search(
        session,
        embedder,
        organization_id=principal.organization_id,
        query=q,
        service=service,
        environment=environment,
        limit=limit,
    )
    return RunbookHits(items=[RunbookHitOut.model_validate(h) for h in hits])


@router.post("/runbooks/reindex", response_model=ReindexResult)
async def reindex_runbooks(
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_RUNBOOKS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    idempotency: IdempotencyDep,
) -> ReindexResult | JSONResponse:
    """Re-embed every active runbook, e.g. after changing the embedding model."""
    if replay := await idempotency.replay(None):
        return replay
    runbooks = list(
        await session.scalars(
            scoped(select(Runbook), Runbook, principal).where(
                Runbook.status == RunbookStatus.ACTIVE
            )
        )
    )
    total = 0
    for runbook in runbooks:
        total += await ingest(session, runbook, embedder)
    await record(
        session,
        principal=principal,
        action="runbook.reindexed",
        resource_type="runbook",
        metadata={"runbooks": len(runbooks), "chunks": total},
    )
    out = ReindexResult(reindexed=len(runbooks), chunks=total)
    await idempotency.commit(status.HTTP_200_OK, out)
    return out


@router.get("/runbooks/{runbook_id}", response_model=RunbookOut)
async def get_runbook(
    runbook_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RunbookOut:
    return RunbookOut.of(await get_owned_or_404(session, Runbook, runbook_id, principal))


@router.put("/runbooks/{runbook_id}", response_model=RunbookOut)
async def update_runbook(
    runbook_id: uuid.UUID,
    body: RunbookWrite,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_RUNBOOKS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    idempotency: IdempotencyDep,
) -> RunbookOut | JSONResponse:
    """Replace the content; a change creates the next version, an identical text changes nothing."""
    if replay := await idempotency.replay(body):
        return replay
    runbook = await get_owned_or_404(session, Runbook, runbook_id, principal)
    doc = _document(body.content)
    if _hash(body.content) == runbook.content_hash:
        return RunbookOut.of(runbook)
    runbook.version = max(runbook.version + 1, doc.version)
    runbook.title = doc.title
    runbook.services = doc.services
    runbook.environment = doc.environment
    runbook.owner = doc.owner
    runbook.content = body.content
    runbook.content_hash = _hash(body.content)
    runbook.status = RunbookStatus.ACTIVE
    if body.source_url:
        runbook.source_url = str(body.source_url)
    await ingest(session, runbook, embedder)
    await record(
        session,
        principal=principal,
        action="runbook.updated",
        resource_type="runbook",
        resource_id=str(runbook.id),
        metadata={"version": runbook.version},
    )
    return await _commit(session, runbook, idempotency)


@router.post("/runbooks/{runbook_id}/archive", response_model=RunbookOut)
async def archive_runbook(
    runbook_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_RUNBOOKS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency: IdempotencyDep,
) -> RunbookOut | JSONResponse:
    if replay := await idempotency.replay(None):
        return replay
    runbook = await get_owned_or_404(session, Runbook, runbook_id, principal)
    runbook.status = RunbookStatus.ARCHIVED
    await record(
        session,
        principal=principal,
        action="runbook.archived",
        resource_type="runbook",
        resource_id=str(runbook.id),
        metadata={"version": runbook.version},
    )
    return await _commit(session, runbook, idempotency)
