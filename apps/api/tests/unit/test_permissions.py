"""The role → permission authorization matrix, cell by cell."""

import pytest

from opspilot_api.auth.permissions import Permission, permissions_for
from opspilot_api.auth.roles import Role

VIEW, OPER, CMDR, ADMIN = (
    Role.VIEWER,
    Role.OPERATOR,
    Role.INCIDENT_COMMANDER,
    Role.ADMINISTRATOR,
)

MATRIX: dict[Permission, set[Role]] = {
    Permission.VIEW_SERVICES: {VIEW, OPER, CMDR, ADMIN},
    Permission.VIEW_INCIDENTS: {VIEW, OPER, CMDR, ADMIN},
    Permission.START_INVESTIGATION: {OPER, CMDR, ADMIN},
    Permission.APPROVE_REMEDIATION: {CMDR, ADMIN},
    Permission.MANAGE_USERS: {ADMIN},
    Permission.MANAGE_RUNBOOKS: {OPER, CMDR, ADMIN},
    Permission.VIEW_AUDIT_LOGS: {CMDR, ADMIN},
    Permission.MANAGE_SERVICES: {OPER, CMDR, ADMIN},
    Permission.MANAGE_INCIDENTS: {OPER, CMDR, ADMIN},
}


def test_matrix_covers_every_permission() -> None:
    assert set(MATRIX) == set(Permission)


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("permission", list(Permission))
def test_role_has_exactly_the_matrix_permissions(role: Role, permission: Permission) -> None:
    assert (permission in permissions_for({role})) is (role in MATRIX[permission])


def test_permissions_combine_across_roles() -> None:
    assert permissions_for({VIEW, OPER}) == permissions_for({VIEW}) | permissions_for({OPER})


def test_no_roles_means_no_permissions() -> None:
    assert permissions_for(set()) == frozenset()
