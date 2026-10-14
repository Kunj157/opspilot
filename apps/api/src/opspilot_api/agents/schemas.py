"""What each agent must return. Every model answer is validated against these."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ToolName = Literal[
    "query_service_metrics",
    "search_service_logs",
    "get_trace_summary",
    "get_service_dependencies",
    "get_recent_deployments",
    "get_kubernetes_rollout_status",
    "search_runbooks",
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
    reason: str = Field(max_length=300)


class ToolPlan(Strict):
    calls: list[PlannedCall] = Field(max_length=4)


class TriageOutput(Strict):
    suspected_service: str = Field(max_length=63)
    reasoning: str = Field(max_length=600)
    focus: list[str] = Field(default_factory=list, max_length=4)


class Hypothesis(Strict):
    description: str = Field(max_length=500)
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[str] = Field(max_length=10)
    contradicting_evidence: list[str] = Field(default_factory=list, max_length=10)


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
    evidence: list[str] = Field(max_length=10)
    runbook_slug: str | None = Field(default=None, max_length=63)
    replicas: int | None = Field(default=None, ge=1, le=20)
