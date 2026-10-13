import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.audit.service import record
from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import get_owned_or_404, scoped
from opspilot_api.db.models import HealthStatus, Service, ServiceDependency
from opspilot_api.db.session import get_session
from opspilot_api.idempotency import Idempotency, idempotency_key

router = APIRouter(prefix="/api/v1", tags=["services"])

SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"
DNS_LABEL = r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
DNS_SUBDOMAIN = r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$"


class ServiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, max_length=2000)
    owner_team: str | None = Field(default=None, max_length=100)
    repository_url: AnyHttpUrl | None = None
    namespace: str | None = Field(default=None, max_length=63, pattern=DNS_LABEL)
    deployment_name: str | None = Field(default=None, max_length=253, pattern=DNS_SUBDOMAIN)

    @field_validator("repository_url")
    @classmethod
    def web_url(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and value.scheme not in {"http", "https"}:
            raise ValueError("must be an http(s) URL")
        return value


class ServiceCreate(ServiceFields):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=2, max_length=63, pattern=SLUG)


class ServiceUpdate(ServiceFields):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=2, max_length=63, pattern=SLUG)


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    owner_team: str | None
    repository_url: str | None
    namespace: str | None
    deployment_name: str | None
    health_status: HealthStatus
    created_at: datetime
    updated_at: datetime


class ServiceList(BaseModel):
    items: list[ServiceOut]


def _conflict() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "A service with this slug already exists")


def _columns(data: ServiceFields, *, exclude_unset: bool) -> dict[str, object]:
    values = data.model_dump(exclude_unset=exclude_unset)
    if values.get("repository_url") is not None:
        values["repository_url"] = str(values["repository_url"])
    return values


@router.get("/services", response_model=ServiceList)
async def list_services(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_SERVICES))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServiceList:
    rows = await session.execute(scoped(select(Service), Service, principal).order_by(Service.name))
    return ServiceList(items=[ServiceOut.model_validate(s) for s in rows.scalars()])


@router.post("/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    body: ServiceCreate,
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_SERVICES))],
    session: Annotated[AsyncSession, Depends(get_session)],
    key: Annotated[str | None, Depends(idempotency_key)],
) -> ServiceOut | JSONResponse:
    idempotency = Idempotency(session, principal, request, key)
    if replay := await idempotency.replay(body):
        return replay
    service = Service(
        organization_id=principal.organization_id, **_columns(body, exclude_unset=False)
    )
    session.add(service)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict() from exc
    await record(
        session,
        principal=principal,
        action="service.created",
        resource_type="service",
        resource_id=str(service.id),
        metadata={"slug": service.slug},
    )
    await session.flush()
    await session.refresh(service)
    out = ServiceOut.model_validate(service)
    await idempotency.remember(status.HTTP_201_CREATED, out.model_dump(mode="json"))
    await session.commit()
    return out


@router.get("/services/{service_id}", response_model=ServiceOut)
async def get_service(
    service_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_SERVICES))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServiceOut:
    return ServiceOut.model_validate(
        await get_owned_or_404(session, Service, service_id, principal)
    )


@router.patch("/services/{service_id}", response_model=ServiceOut)
async def update_service(
    service_id: uuid.UUID,
    body: ServiceUpdate,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_SERVICES))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServiceOut:
    service = await get_owned_or_404(session, Service, service_id, principal)
    changes = _columns(body, exclude_unset=True)
    for field, value in changes.items():
        setattr(service, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict() from exc
    await record(
        session,
        principal=principal,
        action="service.updated",
        resource_type="service",
        resource_id=str(service.id),
        metadata={"changed": sorted(changes)},
    )
    await session.commit()
    await session.refresh(service)
    return ServiceOut.model_validate(service)


class DependenciesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_ids: list[uuid.UUID] = Field(max_length=200)


def _invalid_targets(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"loc": ["body", "target_ids"], "msg": message, "type": "value_error"}],
    )


async def _dependencies(session: AsyncSession, service: Service) -> ServiceList:
    rows = await session.execute(
        select(Service)
        .join(ServiceDependency, ServiceDependency.target_service_id == Service.id)
        .where(ServiceDependency.source_service_id == service.id)
        .order_by(Service.name)
    )
    return ServiceList(items=[ServiceOut.model_validate(s) for s in rows.scalars()])


@router.get("/services/{service_id}/dependencies", response_model=ServiceList)
async def list_dependencies(
    service_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_SERVICES))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServiceList:
    """Services this service calls."""
    return await _dependencies(
        session, await get_owned_or_404(session, Service, service_id, principal)
    )


@router.put("/services/{service_id}/dependencies", response_model=ServiceList)
async def replace_dependencies(
    service_id: uuid.UUID,
    body: DependenciesUpdate,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_SERVICES))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServiceList:
    """Replace the full set of services this service calls."""
    service = await get_owned_or_404(session, Service, service_id, principal)
    targets = sorted(set(body.target_ids), key=str)
    if service.id in targets:
        raise _invalid_targets("a service cannot depend on itself")
    found = await session.scalars(
        scoped(select(Service.id), Service, principal).where(Service.id.in_(targets))
    )
    if len(set(found)) != len(targets):
        # Services in other organizations are reported like missing ones.
        raise _invalid_targets("unknown service")
    await session.execute(
        delete(ServiceDependency).where(ServiceDependency.source_service_id == service.id)
    )
    session.add_all(
        ServiceDependency(
            organization_id=principal.organization_id,
            source_service_id=service.id,
            target_service_id=target,
        )
        for target in targets
    )
    await record(
        session,
        principal=principal,
        action="service.dependencies_updated",
        resource_type="service",
        resource_id=str(service.id),
        metadata={"target_ids": [str(t) for t in targets]},
    )
    await session.flush()
    result = await _dependencies(session, service)
    await session.commit()
    return result
