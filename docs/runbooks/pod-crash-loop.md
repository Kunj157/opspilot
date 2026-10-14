---
title: Pod crash loop
services: [storefront, checkout, payment, inventory, notification]
owner: platform-team
version: 1
---

# Pod crash loop

## Scope

Pods of a demo deployment restart repeatedly (CrashLoopBackOff), so the
service runs with fewer replicas than intended or none.

## Symptoms

- `kube_pod_container_status_restarts_total` increasing
- `kube_deployment_status_replicas_available` below the desired replicas
- Readiness probe failures; gaps in the service's request metrics

## Prerequisites

- `kubectl` access to namespace `demo`; Loki access

## Investigation steps

1. `kubectl -n demo get pods` and find the restarting pods.
2. Read the last logs before the crash: `kubectl -n demo logs <pod> --previous`.
3. Check for a recent rollout or configuration change.
4. Check memory limits against usage (OOMKilled shows in `kubectl describe pod`).

## Safe actions

- Roll back the deployment if the crashes began with the latest release.
- Restart the deployment once if the cause was transient.

## High-risk actions

- Raising resource limits or deleting the deployment.

## Verification

- No restarts for 10 minutes; available replicas equal desired replicas

## Rollback

Revert any change made during the investigation if restarts continue.

## Escalation

Platform team on-call.
