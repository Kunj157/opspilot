import uuid
from dataclasses import dataclass

from opspilot_api.auth.roles import Role


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, resolved from a verified token and the database."""

    user_id: uuid.UUID
    organization_id: uuid.UUID
    organization_slug: str
    subject: str
    email: str | None
    display_name: str
    roles: frozenset[Role]
