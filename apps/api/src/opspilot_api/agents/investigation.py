"""The investigation workflow (LangGraph): triage → observability → deployment → runbook →
synthesis (loops back for more evidence, bounded) → remediation proposal.

Every node is persisted when it finishes, so a restarted worker resumes at the
next node. Limits (rounds, tool calls, tokens, cost, wall time) stop the run
early as a partial result. If the model fails, the planner nodes fall back to
fixed tool plans; synthesis or remediation failure ends the run as partial with
the evidence kept and manual review recommended. Nothing here executes a
remediation: proposals wait for human approval.
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict, cast

import structlog
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.agents import prompts
from opspilot_api.agents.llm import LLM, LLMError, Usage, as_json
from opspilot_api.agents.policy import PROPOSAL_TTL, VERIFICATION_PLAN, Approved, Rejected, evaluate
from opspilot_api.agents.schemas import (
    PlannedCall,
    ProposalDraft,
    Synthesis,
    ToolPlan,
    TriageOutput,
)
from opspilot_api.agents.tools import TOOLS, ToolContext, ToolResult, run_tool
from opspilot_api.db.models import (
    ActorType,
    AgentRun,
    AgentToolCall,
    Evidence,
    Incident,
    IncidentStatus,
    Investigation,
    InvestigationStatus,
    RemediationProposal,
    Runbook,
    Service,
)
from opspilot_api.incidents import service as incidents

log = structlog.get_logger("opspilot.investigation")

AGENT_TOOLS: dict[str, set[str]] = {
    "triage": {"get_service_dependencies", "search_similar_incidents"},
    "observability": {
        "query_service_metrics",
        "search_service_logs",
        "get_trace_summary",
        "get_service_dependencies",
    },
    "deployment": {"get_recent_deployments", "get_kubernetes_rollout_status"},
    "runbook": {"search_runbooks", "search_similar_incidents"},
}
ORDER = ["triage", "observability", "deployment", "runbook", "synthesis", "remediation"]


@dataclass(frozen=True)
class Limits:
    max_rounds: int = 2
    max_tool_calls: int = 24
    max_tokens: int = 80_000
    max_cost_usd: float = 0.50
    max_seconds: float = 300.0


class State(TypedDict, total=False):
    incident_id: str
    organization_id: str
    title: str
    service: str | None
    round: int
    next: str
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    unknowns: list[str]
    summary: str
    enough_evidence: bool
    focus_service: str | None
    runbooks: list[dict[str, Any]]
    deployments: dict[str, dict[str, Any]]
    runbook_excerpts: str
    proposal_id: str | None
    outcome: str
    notes: list[str]


class _Stop(Exception):
    """A limit was reached; end the run as partial."""


ContextFactory = Callable[[uuid.UUID, uuid.UUID], Awaitable[ToolContext]]


class Investigator:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        llm: LLM,
        make_context: ContextFactory,
        *,
        limits: Limits | None = None,
        allowed_namespaces: frozenset[str] = frozenset({"demo"}),
    ) -> None:
        self.sessions = sessions
        self.llm = llm
        self.make_context = make_context
        self.limits = limits or Limits()
        self.allowed_namespaces = allowed_namespaces
        self.graph = self._build()

    # Graph -----------------------------------------------------------------

    def _build(self) -> Any:
        graph = StateGraph(State)

        def route(state: State) -> str:
            return END if state.get("next") == "done" else state.get("next", "triage")

        for name in ORDER:
            graph.add_node(name, cast(Any, self._node(name)))
            graph.add_conditional_edges(name, route)
        graph.add_conditional_edges(START, route)
        return graph.compile()

    def _node(self, name: str) -> Callable[[State], Awaitable[State]]:
        async def run(state: State) -> State:
            self._check_limits()
            handler = getattr(self, f"_{name}")
            updated: State = await handler(state)
            await self._persist(updated, name)
            return updated

        return run

    # Entry point -----------------------------------------------------------

    async def run(self, investigation_id: uuid.UUID) -> InvestigationStatus:
        async with self.sessions() as session:
            investigation = await session.get_one(Investigation, investigation_id)
            incident = await session.get_one(Incident, investigation.incident_id)
            service = (
                await session.get(Service, incident.service_id) if incident.service_id else None
            )
            self.usage_totals = {
                "tool_calls": investigation.tool_calls,
                "input_tokens": investigation.input_tokens,
                "output_tokens": investigation.output_tokens,
                "cost_usd": investigation.cost_usd,
            }
            state: State = dict(investigation.state) or {  # type: ignore[assignment]
                "incident_id": str(incident.id),
                "organization_id": str(incident.organization_id),
                "title": incident.title,
                "service": service.slug if service else None,
                "round": 0,
                "next": "triage",
                "evidence": [],
                "hypotheses": [],
                "unknowns": [],
                "runbooks": [],
                "deployments": {},
                "notes": [],
            }
            if incident.status is IncidentStatus.DETECTED:
                await incidents.transition(
                    session,
                    incident,
                    IncidentStatus.INVESTIGATING,
                    expected_version=incident.version,
                    actor=self._actor(incident.organization_id, "investigator"),
                    reason="automatic investigation started",
                )
            await session.commit()
        self.investigation_id = investigation_id
        self.started = time.monotonic()
        self.context = await self.make_context(
            uuid.UUID(state["organization_id"]), uuid.UUID(state["incident_id"])
        )
        try:
            final: State = await self.graph.ainvoke(state, {"recursion_limit": 50})
        except _Stop as stop:
            return await self._finish(InvestigationStatus.PARTIAL, str(stop))
        status = (
            InvestigationStatus.COMPLETED
            if final.get("outcome") == "completed"
            else InvestigationStatus.PARTIAL
        )
        return await self._finish(status, None)

    # Nodes -----------------------------------------------------------------

    async def _triage(self, state: State) -> State:
        catalog = await self._catalog(state)
        prompt = (
            f"Incident: {state['title']}\n"
            f"Service on the incident: {state.get('service') or 'unknown'}\n"
            f"Catalog services: {', '.join(catalog)}\n"
            f"Evidence so far:\n{self._evidence_text(state)}"
        )
        triage, run_id = await self._ask("triage", prompts.TRIAGE, prompt, TriageOutput)
        suspected = state.get("service")
        if triage is not None and triage.value.suspected_service in catalog:
            suspected = triage.value.suspected_service
            state["notes"].append(f"Triage: {triage.value.reasoning}")
        state["service"] = suspected
        default = [
            PlannedCall(
                tool="get_service_dependencies", service=suspected, reason="triage context"
            ),
            PlannedCall(tool="search_similar_incidents", service=suspected, reason="history"),
        ]
        await self._execute(state, "triage", run_id, default if suspected else [])
        await self._note(
            state, "triage", f"Triage: investigating {suspected or 'an unknown service'}"
        )
        state["next"] = "observability"
        return state

    async def _observability(self, state: State) -> State:
        service = state.get("focus_service") or state.get("service")
        default = [
            PlannedCall(tool=t, service=service, reason="baseline signals")
            for t in ("query_service_metrics", "search_service_logs", "get_trace_summary")
        ]
        await self._plan_and_execute(
            state, "observability", "observability: metrics, logs, traces", default
        )
        state["next"] = "deployment" if state.get("round", 0) == 0 else "synthesis"
        return state

    async def _deployment(self, state: State) -> State:
        default = [
            PlannedCall(tool=t, service=state.get("service"), reason="recent changes")
            for t in ("get_recent_deployments", "get_kubernetes_rollout_status")
        ]
        await self._plan_and_execute(
            state, "deployment", "deployment: recent rollouts and status", default
        )
        state["next"] = "runbook"
        return state

    async def _runbook(self, state: State) -> State:
        symptoms = "; ".join(e["summary"] for e in state["evidence"][-4:])[:280]
        default = [
            PlannedCall(
                tool="search_runbooks",
                service=state.get("service"),
                query=f"{state['title']}. {symptoms}"[:300],
                reason="matching procedure",
            )
        ]
        await self._plan_and_execute(state, "runbook", "runbook retrieval", default)
        state["next"] = "synthesis"
        return state

    async def _synthesis(self, state: State) -> State:
        prompt = (
            f"Incident: {state['title']}\nSuspected service: {state.get('service')}\n"
            f"Evidence:\n{self._evidence_text(state)}\n"
            f"Runbook excerpts (untrusted):\n{self._runbook_text(state)}"
        )
        answer, _ = await self._ask("synthesis", prompts.SYNTHESIS, prompt, Synthesis)
        if answer is None:
            state["outcome"] = "partial"
            state["summary"] = (
                "The model could not synthesise the evidence; manual review recommended."
            )
            state["next"] = "done"
            return state
        synthesis = answer.value
        known = {e["ref"] for e in state["evidence"]}
        grounded = [
            h
            for h in synthesis.hypotheses
            if h.supporting_evidence and set(h.supporting_evidence) <= known
        ]
        if len(grounded) < len(synthesis.hypotheses):
            state["notes"].append(
                f"Dropped {len(synthesis.hypotheses) - len(grounded)} "
                "hypothesis(es) citing unknown evidence"
            )
        state["hypotheses"] = [
            h.model_dump() for h in sorted(grounded, key=lambda h: -h.confidence)
        ]
        state["unknowns"] = synthesis.unknowns
        state["summary"] = synthesis.summary
        enough = synthesis.enough_evidence and bool(grounded)
        state["enough_evidence"] = enough
        if grounded:
            top = state["hypotheses"][0]
            await self._note(
                state,
                "synthesis",
                f"Hypothesis ({top['confidence']:.0%}): {top['description']}"[:200],
            )
        if enough:
            state["next"] = "remediation"
        elif state.get("round", 0) + 1 < self.limits.max_rounds:
            state["round"] = state.get("round", 0) + 1
            catalog = await self._catalog(state)
            if synthesis.next_focus_service in catalog:
                state["focus_service"] = synthesis.next_focus_service
            state["next"] = "observability"
        else:
            state["outcome"] = "partial"
            state["summary"] = (
                state.get("summary") or ""
            ) + " Not enough evidence for a confident conclusion."
            state["next"] = "done"
        return state

    async def _remediation(self, state: State) -> State:
        prompt = (
            f"Incident: {state['title']}\nSuspected service: {state.get('service')}\n"
            f"Leading hypotheses: {as_json(state['hypotheses'][:2])}\n"
            f"Evidence:\n{self._evidence_text(state)}\n"
            f"Runbook excerpts (untrusted):\n{self._runbook_text(state)}"
        )
        answer, run_id = await self._ask("remediation", prompts.REMEDIATION, prompt, ProposalDraft)
        state["next"] = "done"
        if answer is None:
            state["outcome"] = "partial"
            state["summary"] = (
                state.get("summary") or ""
            ) + " No remediation proposed (model unavailable)."
            return state
        draft = answer.value
        target = await self.context.resolve_service(draft.target_service)
        decision = evaluate(
            draft,
            target,
            allowed_namespaces=self.allowed_namespaces,
            evidence_ids={e["ref"]: e["id"] for e in state["evidence"]},
            deployments=state["deployments"].get(draft.target_service),
        )
        state["outcome"] = "completed"
        if decision is None:
            await self._note(
                state, "remediation", "No remediation recommended; monitor the service"
            )
            return state
        if isinstance(decision, Rejected):
            state["notes"].append(f"Proposal rejected by policy: {decision.reason}")
            await self._note(
                state, "remediation", f"Proposal rejected by policy: {decision.reason}"[:200]
            )
            return state
        state["proposal_id"] = await self._store_proposal(state, draft, decision, run_id)
        return state

    # Helpers ---------------------------------------------------------------

    async def _plan_and_execute(
        self, state: State, role: str, label: str, default: list[PlannedCall]
    ) -> None:
        prompt = (
            f"Incident: {state['title']}\nSuspected service: {state.get('service')}\n"
            f"Allowed tools: {self._tool_list(role)}\n"
            f"Calls already made: {', '.join(e['call'] for e in state['evidence']) or 'none'}\n"
            f"Evidence so far:\n{self._evidence_text(state)}"
        )
        plan, run_id = await self._ask(role, prompts.PLANNER.format(role=label), prompt, ToolPlan)
        calls = plan.value.calls if plan is not None and plan.value.calls else default
        await self._execute(state, role, run_id, calls)

    async def _execute(
        self, state: State, role: str, run_id: uuid.UUID | None, calls: list[PlannedCall]
    ) -> None:
        done = {e["call"] for e in state["evidence"]}
        for call in calls:
            schema = TOOLS[call.tool][0] if call.tool in TOOLS else None
            fields = set(schema.model_fields) if schema else set()
            arguments = {
                k: v
                for k, v in call.model_dump(exclude={"tool", "reason"}).items()
                if v is not None and k in fields
            }
            key = f"{call.tool}({as_json(arguments)})"
            if key in done:
                continue
            done.add(key)
            if self.usage_totals["tool_calls"] >= self.limits.max_tool_calls:
                raise _Stop("tool call limit reached")
            started = time.perf_counter()
            result = await run_tool(self.context, call.tool, arguments, allowed=AGENT_TOOLS[role])
            self.usage_totals["tool_calls"] += 1
            await self._record_call(
                state,
                role,
                run_id,
                call.tool,
                arguments,
                result,
                (time.perf_counter() - started) * 1000,
                key,
            )

    async def _ask[T: BaseModel](
        self, agent: str, system: str, prompt: str, schema: type[T]
    ) -> tuple[Any, uuid.UUID]:
        started = datetime.now(UTC)
        status, error, answer = "succeeded", None, None
        usage = Usage()
        try:
            answer = await self.llm.complete_json(system, prompt, schema)
            usage = answer.usage
        except LLMError as exc:
            status, error = "failed", str(exc)[:100]
            log.warning("agent model call failed", agent=agent, error=str(exc))
        self.usage_totals["input_tokens"] += usage.input_tokens
        self.usage_totals["output_tokens"] += usage.output_tokens
        self.usage_totals["cost_usd"] += usage.cost_usd
        async with self.sessions() as session:
            run = AgentRun(
                organization_id=self.context.organization_id,
                investigation_id=self.investigation_id,
                incident_id=self.context.incident_id,
                agent_name=agent,
                status=status if answer is not None else "fallback",
                model_provider=self.llm.provider,
                model_name=self.llm.model,
                prompt_version=prompts.PROMPT_VERSION,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost=usage.cost_usd,
                latency_ms=usage.latency_ms,
                error_code=error,
                output=answer.value.model_dump() if answer is not None else None,
                started_at=started,
                completed_at=datetime.now(UTC),
            )
            session.add(run)
            await session.commit()
            return answer, run.id

    async def _record_call(
        self,
        state: State,
        role: str,
        run_id: uuid.UUID | None,
        tool: str,
        arguments: dict[str, Any],
        result: ToolResult,
        duration_ms: float,
        key: str,
    ) -> None:
        async with self.sessions() as session:
            if run_id is not None:
                session.add(
                    AgentToolCall(
                        organization_id=self.context.organization_id,
                        agent_run_id=run_id,
                        tool_name=tool,
                        arguments=arguments,
                        status="succeeded" if result.ok else "failed",
                        result_summary=result.summary[:2000] or None,
                        error=(result.error or "")[:500] or None,
                        duration_ms=duration_ms,
                    )
                )
            if result.ok and result.evidence is not None:
                draft = result.evidence
                evidence = Evidence(
                    organization_id=self.context.organization_id,
                    incident_id=self.context.incident_id,
                    investigation_id=self.investigation_id,
                    agent_run_id=run_id,
                    evidence_type=draft.evidence_type,
                    source=draft.source,
                    summary=draft.summary[:2000],
                    content=draft.content,
                    query=(draft.query or "")[:2000] or None,
                    time_range_start=draft.time_range_start,
                    time_range_end=draft.time_range_end,
                    confidence=draft.confidence,
                )
                session.add(evidence)
                await session.flush()
                state["evidence"].append(
                    {
                        "ref": f"E{len(state['evidence']) + 1}",
                        "id": str(evidence.id),
                        "type": draft.evidence_type,
                        "source": draft.source,
                        "summary": draft.summary[:400],
                        "agent": role,
                        "call": key,
                    }
                )
                if tool == "search_runbooks":
                    state["runbooks"] = result.data.get("runbooks", [])
                    state["runbook_excerpts"] = result.data.get("excerpts", "")
                if tool == "get_recent_deployments":
                    state["deployments"][arguments.get("service", "")] = result.data
            await session.commit()

    async def _store_proposal(
        self, state: State, draft: ProposalDraft, decision: Approved, run_id: uuid.UUID
    ) -> str:
        async with self.sessions() as session:
            runbook = None
            if draft.runbook_slug:
                runbook = await session.scalar(
                    select(Runbook).where(
                        Runbook.organization_id == self.context.organization_id,
                        Runbook.slug == draft.runbook_slug,
                    )
                )
            proposal = RemediationProposal(
                organization_id=self.context.organization_id,
                incident_id=self.context.incident_id,
                investigation_id=self.investigation_id,
                runbook_id=runbook.id if runbook else None,
                action_type=decision.action,
                description=draft.reason[:2000],
                parameters=decision.parameters,
                risk_level=decision.risk_level,
                verification_plan=VERIFICATION_PLAN,
                evidence_ids=decision.evidence_ids,
                created_by_agent_run_id=run_id,
                expires_at=datetime.now(UTC) + PROPOSAL_TTL,
            )
            session.add(proposal)
            await session.flush()
            incident = await session.get_one(Incident, self.context.incident_id)
            actor = self._actor(incident.organization_id, "remediation")
            await incidents.note(
                session,
                incident,
                actor,
                event_type="incident.remediation_proposed",
                title=_describe(decision)[:200],
                metadata={
                    "proposal_id": str(proposal.id),
                    "action": decision.action.value,
                    **decision.parameters,
                },
            )
            if incident.status is IncidentStatus.INVESTIGATING:
                await incidents.transition(
                    session,
                    incident,
                    IncidentStatus.AWAITING_APPROVAL,
                    expected_version=incident.version,
                    actor=actor,
                    reason="remediation proposed",
                )
            await session.commit()
            return str(proposal.id)

    async def _note(self, state: State, agent: str, title: str) -> None:
        async with self.sessions() as session:
            incident = await session.get_one(Incident, self.context.incident_id)
            await incidents.note(
                session,
                incident,
                self._actor(incident.organization_id, agent),
                event_type="incident.agent_update",
                title=title,
                metadata={"agent": agent},
            )
            await session.commit()

    async def _persist(self, state: State, node: str) -> None:
        async with self.sessions() as session:
            investigation = await session.get_one(Investigation, self.investigation_id)
            investigation.state = dict(state)
            investigation.current_node = node
            investigation.round = state.get("round", 0)
            investigation.tool_calls = int(self.usage_totals["tool_calls"])
            investigation.input_tokens = int(self.usage_totals["input_tokens"])
            investigation.output_tokens = int(self.usage_totals["output_tokens"])
            investigation.cost_usd = float(self.usage_totals["cost_usd"])
            await session.commit()

    async def _finish(self, status: InvestigationStatus, reason: str | None) -> InvestigationStatus:
        async with self.sessions() as session:
            investigation = await session.get_one(Investigation, self.investigation_id)
            state = dict(investigation.state)
            investigation.status = status
            investigation.completed_at = datetime.now(UTC)
            investigation.lease_until = None
            investigation.error = reason
            investigation.result = {
                "summary": state.get("summary")
                or ("Stopped early: " + reason if reason else "No conclusion."),
                "hypotheses": state.get("hypotheses", []),
                "unknowns": state.get("unknowns", []),
                "proposal_id": state.get("proposal_id"),
                "runbooks": state.get("runbooks", []),
                "notes": state.get("notes", []),
                "manual_review": status is not InvestigationStatus.COMPLETED,
            }
            incident = await session.get_one(Incident, investigation.incident_id)
            await incidents.note(
                session,
                incident,
                self._actor(incident.organization_id, "investigator"),
                event_type="incident.investigation_finished",
                title=(
                    "Investigation complete"
                    if status is InvestigationStatus.COMPLETED
                    else "Investigation stopped early; manual review recommended"
                ),
                metadata={"investigation_id": str(investigation.id), "status": status.value},
            )
            await session.commit()
        return status

    def _check_limits(self) -> None:
        if (
            self.usage_totals["input_tokens"] + self.usage_totals["output_tokens"]
            > self.limits.max_tokens
        ):
            raise _Stop("token limit reached")
        if self.usage_totals["cost_usd"] > self.limits.max_cost_usd:
            raise _Stop("cost limit reached")
        if time.monotonic() - self.started > self.limits.max_seconds:
            raise _Stop("time limit reached")

    async def _catalog(self, state: State) -> list[str]:
        async with self.sessions() as session:
            return list(
                await session.scalars(
                    select(Service.slug).where(
                        Service.organization_id == uuid.UUID(state["organization_id"])
                    )
                )
            )

    @staticmethod
    def _tool_list(role: str) -> str:
        return ", ".join(f"{t} ({TOOLS[t][2]})" for t in sorted(AGENT_TOOLS[role]))

    @staticmethod
    def _evidence_text(state: State) -> str:
        return (
            "\n".join(f"{e['ref']} [{e['source']}] {e['summary']}" for e in state["evidence"])
            or "none yet"
        )

    @staticmethod
    def _runbook_text(state: State) -> str:
        return (state.get("runbook_excerpts") or "none")[:4000]

    @staticmethod
    def _actor(organization_id: uuid.UUID, agent: str) -> incidents.Actor:
        return incidents.Actor(ActorType.AGENT, f"agent:{agent}", organization_id)


def _describe(decision: Approved) -> str:
    p = decision.parameters
    match decision.action.value:
        case "ROLLBACK_DEPLOYMENT":
            target = f"revision {p['to_revision']} ({p.get('to_version')})"
            return f"Proposed: roll back {p['deployment']} to {target}"
        case "RESTART_DEPLOYMENT":
            return f"Proposed: restart {p['deployment']}"
        case "SCALE_DEPLOYMENT":
            return f"Proposed: scale {p['deployment']} to {p['replicas']} replicas"
        case _:
            return f"Proposed: pause the rollout of {p['deployment']}"
