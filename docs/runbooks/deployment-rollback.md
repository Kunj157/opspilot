---
title: Deployment rollback
services: [storefront, checkout, payment, inventory, notification]
owner: platform-team
version: 1
---

# Deployment rollback

## Scope

Return a demo deployment to its previous rollout revision when a new release
causes errors or latency. This is the standard remediation for a faulty
release in namespace `demo`.

## Symptoms

- Errors or latency started within minutes of a new rollout revision
- The newest revision's change cause names a new version

## Prerequisites

- An incident with evidence that the latest release is the likely cause
- Approval from an incident commander (OpsPilot requires it before executing)

## Investigation steps

1. `kubectl -n demo rollout history deployment/<name>` and note the current and previous revisions.
2. Confirm the previous revision was healthy before the release.
3. Check that no data migration in the new release prevents running the old one.

## Safe actions

- `kubectl -n demo rollout undo deployment/<name>` (previous revision)
- Watch `kubectl -n demo rollout status deployment/<name>` until complete

## High-risk actions

- Rolling back more than one revision, or rolling back several services at once.

## Verification

- Rollout complete and all pods Ready
- Error rate below 2% and p95 latency normal for 5 consecutive minutes
- The incident's detector records the recovery

## Rollback

If the previous revision is also unhealthy, roll forward to the revision that was live before the rollback and escalate.

## Escalation

Platform team on-call, then the owner of the affected service.
