"""The deterministic remediation policy: targets, evidence, and rollback attribution."""

import pytest

from opspilot_api.agents.policy import Approved, Rejected, evaluate
from opspilot_api.agents.schemas import ProposalDraft
from opspilot_api.agents.tools import ServiceTarget
from opspilot_api.db.models import RemediationAction

CHECKOUT = ServiceTarget("1", "checkout", "Checkout", "demo", "checkout")
EVIDENCE = {"E1": "id-1", "E2": "id-2"}


def deployments(
    before: float | None, now: float | None, previous: bool = True
) -> dict[str, object]:
    return {
        "latest": {"revision": 7, "version": "1.4.2"},
        "previous": {"revision": 6, "version": "1.0.0"} if previous else None,
        "error_rate_before_latest": before,
        "error_rate_now": now,
    }


def draft(
    action: str = "ROLLBACK_DEPLOYMENT", evidence: list[str] | None = None, **extra: object
) -> ProposalDraft:
    return ProposalDraft.model_validate(
        {
            "action_type": action,
            "target_service": "checkout",
            "reason": "r",
            "evidence": evidence or ["E1"],
            **extra,
        }
    )


def decide(
    d: ProposalDraft, deps: dict[str, object] | None = None, target: ServiceTarget | None = CHECKOUT
) -> object:
    return evaluate(
        d, target, allowed_namespaces=frozenset({"demo"}), evidence_ids=EVIDENCE, deployments=deps
    )


def test_a_rollback_of_the_release_that_broke_things_is_allowed() -> None:
    decision = decide(draft(), deployments(before=0.0, now=0.45))

    assert isinstance(decision, Approved)
    assert decision.parameters["to_revision"] == 6
    assert decision.evidence_ids == ["id-1"]


@pytest.mark.parametrize(
    ("before", "now", "why"),
    [
        (0.16, 0.19, "errors did not begin with the latest release"),  # already failing before
        (0.0, 0.01, "errors did not begin with the latest release"),  # not failing now
        (None, 0.45, "unknown"),
    ],
)
def test_rollbacks_must_undo_the_release_that_introduced_the_errors(
    before: float | None, now: float, why: str
) -> None:
    decision = decide(draft(), deployments(before=before, now=now))

    assert isinstance(decision, Rejected)
    assert why in decision.reason


def test_no_previous_revision_means_no_rollback() -> None:
    assert isinstance(decide(draft(), deployments(0.0, 0.5, previous=False)), Rejected)


def test_targets_and_evidence_are_checked() -> None:
    foreign = ServiceTarget("2", "dns", "DNS", "kube-system", "coredns")

    assert isinstance(decide(draft("RESTART_DEPLOYMENT"), target=None), Rejected)
    assert isinstance(decide(draft("RESTART_DEPLOYMENT"), target=foreign), Rejected)
    assert isinstance(decide(draft("RESTART_DEPLOYMENT", evidence=["E9"])), Rejected)
    assert isinstance(decide(draft("RESTART_DEPLOYMENT")), Approved)


def test_scaling_is_bounded_and_no_action_proposes_nothing() -> None:
    assert isinstance(decide(draft("SCALE_DEPLOYMENT", replicas=12)), Rejected)
    scaled = decide(draft("SCALE_DEPLOYMENT", replicas=3))
    assert isinstance(scaled, Approved)
    assert scaled.action is RemediationAction.SCALE_DEPLOYMENT
    assert decide(draft("NO_ACTION")) is None
