"""What each agent must return. Every model answer is validated against these."""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_REF = re.compile(r"\bE(\d{1,3})\b")


def evidence_refs(values: Any) -> Any:
    """Accept "E4" or a line that starts with it ("E4 [kubernetes] ..."), keep only the refs."""
    if not isinstance(values, list):
        return values
    refs = []
    for value in values:
        match = _REF.search(str(value))
        if match and f"E{match.group(1)}" not in refs:
            refs.append(f"E{match.group(1)}")
    return refs


ToolName = Literal[
    "query_service_metrics",
    "search_service_logs",
    "get_trace_summary",
    "get_service_dependencies",
    "get_recent_deployments",
    "get_kubernetes_rollout_status",
    "get_recent_configuration_changes",
    "get_commit_metadata",
    "search_runbooks",
    "get_runbook",
    "search_similar_incidents",
]

ActionType = Literal[
    "ROLLBACK_DEPLOYMENT", "RESTART_DEPLOYMENT", "SCALE_DEPLOYMENT", "PAUSE_ROLLOUT", "NO_ACTION"
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlannedCall(Strict):
    tool: ToolName
    service: str | None = Field(default=None, max_length=63)
    minutes: int | None = Field(default=None, ge=1, le=180)
    query: str | None = Field(default=None, max_length=300)
    runbook: str | None = Field(default=None, max_length=63)
    reason: str = Field(max_length=300)


class ToolPlan(Strict):
    calls: list[PlannedCall] = Field(max_length=4)


class TriageOutput(Strict):
    suspected_service: str = Field(max_length=63)
    reasoning: str = Field(max_length=600)
    focus: list[str] = Field(default_factory=list, max_length=4)


class Hypothesis(Strict):
    description: str = Field(max_length=500)
    confidence: float = Field(ge=0, le=1, description="Between 0 and 1")
    supporting_evidence: list[str] = Field(
        max_length=10, description="Evidence references, e.g. E2"
    )
    contradicting_evidence: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("confidence", mode="before")
    @classmethod
    def percent_to_fraction(cls, value: Any) -> Any:
        # Some models answer 80 for 80%.
        if isinstance(value, int | float) and 1 < value <= 100:
            return value / 100
        return value

    _refs = field_validator("supporting_evidence", "contradicting_evidence", mode="before")(
        lambda cls, v: evidence_refs(v)
    )


class Synthesis(Strict):
    summary: str = Field(max_length=800)
    hypotheses: list[Hypothesis] = Field(max_length=4)
    unknowns: list[str] = Field(default_factory=list, max_length=5)
    enough_evidence: bool
    next_focus_service: str | None = Field(default=None, max_length=63)


class ProposalDraft(Strict):
    action_type: ActionType
    target_service: str = Field(max_length=63)
    reason: str = Field(max_length=600)
    evidence: list[str] = Field(max_length=10, description="Evidence references, e.g. E2")
    runbook_slug: str | None = Field(default=None, max_length=63)
    replicas: int | None = Field(default=None, ge=1, le=20)

    _refs = field_validator("evidence", mode="before")(lambda cls, v: evidence_refs(v))


class Finding(Strict):
    statement: str = Field(max_length=500)
    # confirmed: shown directly by evidence; strong/weak: hypotheses; unknown: open question.
    certainty: Literal["confirmed", "strong_hypothesis", "weak_hypothesis", "unknown"]
    evidence: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="References of the evidence this statement relies on, e.g. ['E4', 'E7']",
    )

    _refs = field_validator("evidence", mode="before")(lambda cls, v: evidence_refs(v))


class PostmortemDraft(Strict):
    summary: str = Field(max_length=1200)
    impact: str = Field(max_length=800)
    root_cause: Finding
    findings: list[Finding] = Field(max_length=8)
    resolution: str = Field(max_length=800)
    follow_ups: list[str] = Field(max_length=6)
