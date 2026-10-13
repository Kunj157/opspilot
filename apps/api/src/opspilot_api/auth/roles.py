import enum


class Role(enum.StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    INCIDENT_COMMANDER = "incident-commander"
    ADMINISTRATOR = "administrator"


APPLICATION_ROLES = frozenset(role.value for role in Role)
