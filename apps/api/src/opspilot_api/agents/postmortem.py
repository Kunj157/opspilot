"""Postmortem drafting for resolved incidents.

The model may only cite collected evidence (E1, E2, ...); findings that cite
anything else lose their citations and are demoted to "unknown". The
timeline is taken from the incident events, never from the model. If the
model fails, a template built from the record is stored instead.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.agents import prompts
from opspilot_api.agents.llm import LLM, LLMError, as_json
from opspilot_api.agents.schemas import Finding, PostmortemDraft
from opspilot_api.db.models import (
    Evidence,
    Incident,
    IncidentEvent,
    Investigation,
    Postmortem,
    RemediationProposal,
    Service,
)
from opspilot_api.ops_metrics import AGENT_RUNS

log = structlog.get_logger("opspilot.postmortem")

SYSTEM = (
    "You are OpsPilot's postmortem writer. Draft a blameless postmortem from the record below. "
    "Use only the evidence given. Every finding and the root cause must list the references "
    'they rely on in their evidence field (for example ["E4", "E7"]); a statement without '
    "references counts as unknown. Label each: confirmed (directly shown by evidence), "
    "strong_hypothesis, weak_hypothesis, or unknown. "
    "Never invent numbers, times, or causes. Answer with JSON only."
)


def _ground(finding: Finding, known: set[str]) -> Finding:
    cited = [ref for ref in finding.evidence if ref in known]
    if finding.certainty != "unknown" and not cited:
        return Finding(statement=finding.statement, certainty="unknown", evidence=[])
    return finding.model_copy(update={"evidence": cited})


async def generate(
    sessions: async_sessionmaker[AsyncSession], llm: LLM, incident_id: uuid.UUID
) -> Postmortem:
    async with sessions() as session:
        incident = await session.get_one(Incident, incident_id)
        service = await session.get(Service, incident.service_id) if incident.service_id else None
        events = list(
            await session.scalars(
                select(IncidentEvent)
                .where(IncidentEvent.incident_id == incident_id)
                .order_by(IncidentEvent.sequence)
            )
        )
        evidence = list(
            await session.scalars(
                select(Evidence)
                .where(Evidence.incident_id == incident_id)
                .order_by(Evidence.created_at)
            )
        )
        investigation = await session.scalar(
            select(Investigation)
            .where(Investigation.incident_id == incident_id)
            .order_by(Investigation.created_at.desc())
        )
        proposals = list(
            await session.scalars(
                select(RemediationProposal).where(RemediationProposal.incident_id == incident_id)
            )
        )
    refs = {f"E{i + 1}": e for i, e in enumerate(evidence)}
    timeline = [
        {
            "at": e.created_at.isoformat(),
            "event": e.title,
            "actor": f"{e.actor_type.value}:{e.actor_id}",
        }
        for e in events
    ]
    duration = (
        (incident.resolved_at - incident.started_at).total_seconds() / 60
        if incident.resolved_at
        else None
    )
    slug = service.slug if service else "unknown"
    resolved = incident.resolved_at.isoformat() if incident.resolved_at else "not yet"
    result = (investigation.result or {}) if investigation else {}
    lines = [
        f"Incident: {incident.title} (severity {incident.severity.value}, service {slug})",
        f"Started {incident.started_at.isoformat()}, resolved {resolved}"
        + (f", duration {duration:.0f} min" if duration is not None else ""),
        "Timeline:",
        *(f"- {t['at']} {t['event']} ({t['actor']})" for t in timeline),
        "Evidence:",
        *(f"{ref} [{e.source}] {e.summary}" for ref, e in refs.items()),
        f"Investigation result: {as_json(result)}",
        "Remediation: "
        + "; ".join(
            f"{p.action_type.value} {as_json(p.parameters)} ({p.status.value})" for p in proposals
        ),
    ]
    record = "\n".join(lines)
    content: dict[str, Any]
    generated_by = f"{llm.provider}:{llm.model}"
    try:
        draft = (await llm.complete_json(SYSTEM, record[:20000], PostmortemDraft)).value
        known = set(refs)
        draft = draft.model_copy(
            update={
                "root_cause": _ground(draft.root_cause, known),
                "findings": [_ground(f, known) for f in draft.findings],
            }
        )
        content = draft.model_dump()
        AGENT_RUNS.labels("postmortem", "completed").inc()
    except LLMError as exc:
        AGENT_RUNS.labels("postmortem", "fallback").inc()
        log.warning("postmortem model call failed", incident_id=str(incident_id), error=str(exc))
        generated_by = "template"
        content = {
            "summary": f"{incident.title}. Drafted from the incident record "
            "because the model was unavailable.",
            "impact": f"{service.name if service else 'A service'} was affected"
            + (f" for about {duration:.0f} minutes." if duration is not None else "."),
            "root_cause": {
                "statement": "Not determined automatically.",
                "certainty": "unknown",
                "evidence": [],
            },
            "findings": [
                {"statement": e.summary, "certainty": "confirmed", "evidence": [ref]}
                for ref, e in refs.items()
            ][:8],
            "resolution": "; ".join(f"{p.action_type.value} ({p.status.value})" for p in proposals)
            or "See the timeline.",
            "follow_ups": ["Review this incident manually."],
        }
    content["timeline"] = timeline
    content["evidence"] = {
        ref: {"id": str(e.id), "source": e.source, "summary": e.summary} for ref, e in refs.items()
    }
    async with sessions() as session:
        postmortem = await session.scalar(
            select(Postmortem).where(Postmortem.incident_id == incident_id)
        )
        if postmortem is None:
            postmortem = Postmortem(
                organization_id=incident.organization_id, incident_id=incident_id
            )
            session.add(postmortem)
        postmortem.status = "ready"
        postmortem.content = content
        postmortem.generated_by = generated_by
        postmortem.prompt_version = prompts.PROMPT_VERSION
        await session.commit()
        await session.refresh(postmortem)
        return postmortem


async def pending(sessions: async_sessionmaker[AsyncSession], limit: int = 5) -> list[uuid.UUID]:
    """Resolved incidents whose postmortem is missing or was requested again."""
    from opspilot_api.db.models import IncidentStatus

    async with sessions() as session:
        missing = await session.scalars(
            select(Incident.id)
            .outerjoin(Postmortem, Postmortem.incident_id == Incident.id)
            .where(
                Incident.status == IncidentStatus.RESOLVED,
                (Postmortem.id.is_(None)) | (Postmortem.status == "pending"),
            )
            .order_by(Incident.resolved_at.desc())
            .limit(limit)
        )
        return list(missing)
