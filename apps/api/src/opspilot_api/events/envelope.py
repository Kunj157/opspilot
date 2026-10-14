"""Event envelope v1 and the versioned topics incident events are published to.

Payloads carry identifiers, types, and states only: no free text written by
people (comments, descriptions) and nothing from telemetry, so a topic never
holds sensitive content.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opspilot_api.db.models import IncidentEvent

ENVELOPE_VERSION: Literal[1] = 1


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID
    event_type: str = Field(pattern=r"^[a-z]+(\.[a-z_]+)+\.v\d+$")
    event_version: Literal[1]
    organization_id: uuid.UUID
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None
    occurred_at: datetime
    producer: str
    payload: dict[str, Any]


# Timeline event type → topic. Status changes publish only when they resolve.
TOPICS = {
    "incident.anomaly_detected": "telemetry.anomaly.detected.v1",
    "incident.created": "incident.created.v1",
    "incident.investigation_requested": "incident.investigation.requested.v1",
    "incident.evidence_collected": "incident.evidence.collected.v1",
    "incident.remediation_proposed": "incident.remediation.proposed.v1",
    "incident.remediation_approved": "incident.remediation.approved.v1",
    "incident.remediation_executed": "incident.remediation.completed.v1",
    "incident.remediation_failed": "incident.remediation.completed.v1",
    "incident.verification_passed": "incident.verification.completed.v1",
    "incident.verification_failed": "incident.verification.completed.v1",
}
RESOLVED_TOPIC = "incident.resolved.v1"
ALL_TOPICS = sorted({*TOPICS.values(), RESOLVED_TOPIC})
# Metadata fields that may leave the database; everything else stays.
SAFE_METADATA = {
    "severity",
    "source",
    "from",
    "to",
    "proposal_id",
    "proposal_version",
    "action_type",
    "execution_id",
    "investigation_id",
    "status",
    "service_id",
    "detector",
    "failure_category",
    "score",
    "threshold",
    "agent",
    "evidence_count",
    "evidence_ids",
    "evidence_types",
}


def dead_letter(topic: str) -> str:
    return f"{topic}.dlq"


def topic_for(event: IncidentEvent) -> str | None:
    if event.event_type == "incident.status_changed":
        return RESOLVED_TOPIC if event.metadata_json.get("to") == "RESOLVED" else None
    return TOPICS.get(event.event_type)


def to_envelope(event: IncidentEvent, topic: str) -> Envelope:
    metadata = event.metadata_json or {}
    payload: dict[str, Any] = {
        "incident_id": str(event.incident_id),
        "sequence": event.sequence,
        "timeline_event_type": event.event_type,
        "actor_type": event.actor_type.value,
        **{k: v for k, v in metadata.items() if k in SAFE_METADATA},
    }
    if event.event_type == "incident.remediation_executed":
        payload["outcome"] = "succeeded"
    if event.event_type == "incident.remediation_failed":
        payload["outcome"] = "failed"
    if event.event_type.startswith("incident.verification_"):
        payload["outcome"] = event.event_type.removeprefix("incident.verification_")
    return Envelope(
        event_id=event.id,
        event_type=topic,
        event_version=ENVELOPE_VERSION,
        organization_id=event.organization_id,
        correlation_id=event.incident_id,
        occurred_at=event.created_at,
        producer="api",
        payload=payload,
    )
