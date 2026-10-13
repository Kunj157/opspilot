# ADR-004: Live incident updates via PostgreSQL NOTIFY

- Status: Accepted
- Date: 2026-10-13

## Context

The dashboard and incident pages need live updates (plan §6.2, §13) over
Server-Sent Events. Several API instances may serve streams, and incident
changes will come from the API now and from background workers later
(agents, remediation, verification). A subscriber must never see a change
that was rolled back, and must not miss changes during reconnects.

## Decision

- A trigger on `incident_events` calls `pg_notify('incident_events', …)` with
  only identifiers (sequence, organization, incident). PostgreSQL delivers
  notifications **only when the inserting transaction commits**.
- Each API process holds one `LISTEN` connection (`EventBroker`) and wakes
  matching SSE subscribers. Subscribers then read events from the table by
  `sequence > last sent`, so coalesced or missed wake-ups lose nothing.
- After the listener reconnects, every subscriber is woken once to catch up.
- Clients resume with `Last-Event-ID` (the event sequence).

## Consequences

- Any writer is covered automatically, including future workers, without
  remembering to publish.
- Event payloads never carry sensitive data; the stream re-reads rows with
  the subscriber's own tenant filter.
- One extra database connection per API process.
- Throughput is bounded by PostgreSQL NOTIFY, ample for incident volumes.
  Phase 11 introduces Redpanda for the broader event bus; this ADR stays for
  UI fan-out unless measurements say otherwise.

## Alternatives considered

- **Redis pub/sub published by the API after commit** — rejected: a crash
  between commit and publish drops the update, and every writer must
  remember to publish.
- **Polling** — rejected: latency or load trade-off with no upside.
