---
title: Payment timeout
services: [payment, checkout]
owner: payments-team
version: 1
---

# Payment timeout

## Scope

Payment responds too slowly, so checkout gives up after its 2 second timeout
and orders fail. Applies to the `payment` deployment in namespace `demo`.

## Symptoms

- `http_request_duration_seconds` p95 for payment above 2 s
- Checkout dependency calls to payment with status `error` (timeouts) and checkout returning 502
- Long `POST /charge` spans in Tempo

## Prerequisites

- Grafana, Prometheus, and Tempo access
- `kubectl` access to namespace `demo`

## Investigation steps

1. Compare payment p95 latency with checkout's error rate on the Demo shop dashboard.
2. Check `service_dependency_requests_total{service="checkout",target="payment"}` by status.
3. Check payment's rollout history for a recent release: `kubectl -n demo rollout history deployment/payment`.
4. Look at a slow trace: which span inside payment is slow?

## Safe actions

- Roll back payment if the latency began with its latest release.
- Restart payment if a single pod is slow and the release is old.

## High-risk actions

- Raising checkout's timeout or disabling payment checks. Requires the payments owner.

## Verification

- Payment p95 under 300 ms and checkout's error rate under 2% for 5 minutes

## Rollback

Undo the rollback (roll forward) if latency does not improve, then escalate.

## Escalation

Payments team on-call.
