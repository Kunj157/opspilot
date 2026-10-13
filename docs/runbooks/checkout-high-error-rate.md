---
title: Checkout high error rate
services: [checkout, storefront]
owner: shop-team
version: 1
---

# Checkout high error rate

## Scope

Checkout returns HTTP 5xx for a sustained share of orders, so customers cannot
complete purchases. Applies to the `checkout` deployment in namespace `demo`.

## Symptoms

- `http_errors_total{service="checkout"}` rising; error rate above 5% for several minutes
- Storefront checkouts fail with 502 while browsing (`/api/products`) still works
- Error spans on `POST /orders` in Tempo; `request served` log lines with `level=error`
- Often follows a new checkout release (a new rollout revision)

## Prerequisites

- Read access to Grafana (Demo shop dashboard), Prometheus, Loki, and Tempo
- `kubectl` access to namespace `demo` for rollout history and rollback

## Investigation steps

1. Confirm the error rate per service on the Demo shop dashboard; note when it started.
2. Check whether checkout's dependencies (payment, inventory, notification) are failing too. If payment is failing, follow **Payment timeout**.
3. List recent checkout rollouts: `kubectl -n demo rollout history deployment/checkout`. Compare the start of the errors with the newest revision's change cause and `SERVICE_VERSION`.
4. Open an error trace from Tempo and read the failing span's `error.type`.
5. Search checkout logs in Loki for the failing trace ID to see the error message.

## Safe actions

- Roll back checkout to the previous revision when the errors began with the latest release (see **Deployment rollback**).
- Restart the checkout deployment when no release coincides and pods look unhealthy.

## High-risk actions

- Scaling checkout to zero, deleting pods by hand, or changing payment configuration. Not allowed without an incident commander.

## Verification

- Checkout error rate below 2% for 5 consecutive minutes
- Storefront checkouts return 200; no new error spans on `POST /orders`
- p95 latency back within normal range

## Rollback

If a rollback makes things worse, roll forward to the revision that was live before the rollback and escalate.

## Escalation

Shop team on-call; if payments are affected, also the payments owner.
