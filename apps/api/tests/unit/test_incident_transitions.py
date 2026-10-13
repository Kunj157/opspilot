"""Every pair of states against the state machine in DEVELOPMENT_PLAN.md §13."""

import itertools

import pytest

from opspilot_api.db.models import IncidentStatus as S
from opspilot_api.incidents.state_machine import ALLOWED_TRANSITIONS, can_transition

EXPECTED = {
    (S.DETECTED, S.INVESTIGATING),
    (S.INVESTIGATING, S.AWAITING_APPROVAL),
    (S.INVESTIGATING, S.MONITORING),
    (S.AWAITING_APPROVAL, S.REMEDIATING),
    (S.AWAITING_APPROVAL, S.REJECTED),
    (S.REMEDIATING, S.VERIFYING),
    (S.VERIFYING, S.RESOLVED),
    (S.VERIFYING, S.INVESTIGATING),
    (S.REJECTED, S.MONITORING),
    (S.MONITORING, S.RESOLVED),
}


@pytest.mark.parametrize(("source", "target"), list(itertools.product(S, S)))
def test_transition_allowed_exactly_as_in_the_plan(source: S, target: S) -> None:
    assert can_transition(source, target) is ((source, target) in EXPECTED)


def test_resolved_is_terminal() -> None:
    assert ALLOWED_TRANSITIONS[S.RESOLVED] == frozenset()


def test_every_state_is_reachable_from_detected() -> None:
    reached, frontier = {S.DETECTED}, [S.DETECTED]
    while frontier:
        for nxt in ALLOWED_TRANSITIONS[frontier.pop()]:
            if nxt not in reached:
                reached.add(nxt)
                frontier.append(nxt)
    assert reached == set(S)
