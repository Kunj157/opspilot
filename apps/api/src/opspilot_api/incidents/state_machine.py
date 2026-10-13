"""Allowed incident status transitions."""

from opspilot_api.db.models import IncidentStatus as S

ALLOWED_TRANSITIONS: dict[S, frozenset[S]] = {
    S.DETECTED: frozenset({S.INVESTIGATING}),
    S.INVESTIGATING: frozenset({S.AWAITING_APPROVAL, S.MONITORING}),
    S.AWAITING_APPROVAL: frozenset({S.REMEDIATING, S.REJECTED}),
    S.REMEDIATING: frozenset({S.VERIFYING}),
    S.VERIFYING: frozenset({S.RESOLVED, S.INVESTIGATING}),
    S.REJECTED: frozenset({S.MONITORING}),
    S.MONITORING: frozenset({S.RESOLVED}),
    S.RESOLVED: frozenset(),
}


def can_transition(source: S, target: S) -> bool:
    return target in ALLOWED_TRANSITIONS[source]
