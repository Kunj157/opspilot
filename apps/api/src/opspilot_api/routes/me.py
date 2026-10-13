import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from opspilot_api.auth.dependencies import CurrentPrincipal
from opspilot_api.auth.roles import Role

router = APIRouter(prefix="/api/v1", tags=["identity"])


class OrganizationRef(BaseModel):
    id: uuid.UUID
    slug: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str
    organization: OrganizationRef
    roles: list[Role]


@router.get("/me", response_model=MeResponse)
async def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(
        id=principal.user_id,
        email=principal.email,
        display_name=principal.display_name,
        organization=OrganizationRef(
            id=principal.organization_id, slug=principal.organization_slug
        ),
        roles=sorted(principal.roles),
    )
