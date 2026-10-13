---
title: Database connection exhaustion
services: [checkout, inventory]
owner: platform-team
version: 1
---

# Database connection exhaustion

## Scope

A service cannot get database connections, so requests queue and fail.

## Symptoms

- Rising latency followed by 5xx on the affected service
- Log lines mentioning connection pool timeouts
- A traffic spike or a release that changed pool settings

## Prerequisites

- Grafana and Loki access; `kubectl` access to namespace `demo`

## Investigation steps

1. Compare request rate with latency: did traffic spike?
2. Search the service's logs for pool or connection timeout messages.
3. Check whether the latest release changed pool size or timeouts.

## Safe actions

- Roll back a release that changed pool settings.
- Scale the service within its configured bounds if traffic spiked.

## High-risk actions

- Raising the database's connection limit or restarting the database.

## Verification

- No pool timeout logs and error rate below 2% for 5 minutes

## Rollback

Scale back to the original replica count once traffic normalises.

## Escalation

Platform team on-call, then the database owner.
