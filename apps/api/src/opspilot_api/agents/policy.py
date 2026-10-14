"""Deterministic remediation policy. The model proposes; this code decides what is allowed.

Parameters are derived from the catalog and collected evidence, never from model
text, so no generated command or target can reach execution.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from opspilot_api.agents.schemas import ProposalDraft
from opspilot_api.agents.tools import ServiceTarget
from opspilot_api.db.models import RemediationAction

RISK = {
    RemediationAction.ROLLBACK_DEPLOYMENT: "medium",
    RemediationAction.RESTART_DEPLOYMENT: "medium",
    RemediationAction.SCALE_DEPLOYMENT: "medium",
    # Pausing changes no pods: it only stops a rollout from going further, and resumes cleanly.
    RemediationAction.PAUSE_ROLLOUT: "low",
}
MAX_REPLICAS = 6
# A rollback must undo a release that introduced the errors: low before it, high after.
HEALTHY_ERROR_RATE = 0.02
FAILING_ERROR_RATE = 0.05
PROPOSAL_TTL = timedelta(minutes=30)
VERIFICATION_PLAN: dict[str, Any] = {
    "require_rollout_complete": True,
    "rollout_timeout_minutes": 5,
    "window_minutes": 3,
    "max_error_rate": 0.02,
    "max_p95_ratio_to_baseline": 1.5,
}
# A paused rollout never completes: verification waits for it to report paused instead.
PAUSE_VERIFICATION_PLAN: dict[str, Any] = {
    **VERIFICATION_PLAN,
    "require_rollout_complete": False,
    "require_paused": True,
}


def verification_plan(action: RemediationAction) -> dict[str, Any]:
    return (
        PAUSE_VERIFICATION_PLAN if action is RemediationAction.PAUSE_ROLLOUT else VERIFICATION_PLAN
    )


@dataclass(frozen=True)
class Approved:
    action: RemediationAction
    parameters: dict[str, Any]
    risk_level: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class Rejected:
    reason: str


def evaluate(
    draft: ProposalDraft,
    target: ServiceTarget | None,
    *,
    allowed_namespaces: frozenset[str],
    evidence_ids: dict[str, str],
    deployments: dict[str, Any] | None,
) -> Approved | Rejected | None:
    """None for NO_ACTION; otherwise the policy decision."""
    if draft.action_type == "NO_ACTION":
        return None
    action = RemediationAction(draft.action_type)
    if target is None:
        return Rejected(f"{draft.target_service!r} is not a catalog service")
    if not target.namespace or not target.deployment:
        return Rejected(f"{target.slug} has no namespace and deployment")
    if target.namespace not in allowed_namespaces:
        return Rejected(f"namespace {target.namespace!r} is not allowed for remediation")
    cited = [evidence_ids[ref] for ref in draft.evidence if ref in evidence_ids]
    if not cited:
        return Rejected("the proposal cites no collected evidence")
    parameters: dict[str, Any] = {"namespace": target.namespace, "deployment": target.deployment}
    if action is RemediationAction.ROLLBACK_DEPLOYMENT:
        previous = (deployments or {}).get("previous")
        if not previous:
            return Rejected("no earlier revision is known to roll back to")
        before = (deployments or {}).get("error_rate_before_latest")
        now = (deployments or {}).get("error_rate_now")
        if before is None or now is None:
            return Rejected("error rates around the latest rollout are unknown")
        if before >= HEALTHY_ERROR_RATE or now < FAILING_ERROR_RATE:
            return Rejected(
                f"errors did not begin with the latest release (before {before:.1%}, now {now:.1%})"
            )
        parameters["to_revision"] = previous["revision"]
        parameters["from_version"] = (deployments or {}).get("latest", {}).get("version")
        parameters["to_version"] = previous.get("version")
    if action is RemediationAction.PAUSE_ROLLOUT:
        rollout = (deployments or {}).get("rollout")
        if not rollout:
            return Rejected("the rollout status is unknown")
        if rollout.get("complete"):
            return Rejected("the rollout is already complete; there is nothing to pause")
        latest = (deployments or {}).get("latest") or {}
        parameters["revision"] = latest.get("revision")
        parameters["version"] = latest.get("version")
    if action is RemediationAction.SCALE_DEPLOYMENT:
        if draft.replicas is None or not 1 <= draft.replicas <= MAX_REPLICAS:
            return Rejected(f"scaling must name 1-{MAX_REPLICAS} replicas")
        parameters["replicas"] = draft.replicas
    return Approved(action, parameters, RISK[action], cited)
