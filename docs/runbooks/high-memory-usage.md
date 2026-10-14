---
title: High memory usage
services: [storefront, checkout, payment, inventory, notification]
owner: platform-team
version: 1
---

# High memory usage

## Scope

A service's memory grows until pods hit their limit and are OOM-killed.

## Symptoms

- `process_memory_usage` (container memory) climbing steadily
- Pods restarting with reason OOMKilled; latency rising before each restart

## Prerequisites

- Grafana access; `kubectl` access to namespace `demo`

## Investigation steps

1. Plot memory per pod over the last hours: steady growth suggests a leak.
2. Check whether the growth began with a release.
3. `kubectl -n demo describe pod <pod>` for OOMKilled terminations.

## Safe actions

- Roll back the release that introduced the growth.
- Restart the deployment to buy time while investigating.

## High-risk actions

- Raising memory limits without understanding the growth.

## Verification

- Memory flat for 30 minutes; no OOMKilled restarts

## Rollback

Revert limit changes made during the incident.

## Escalation

Owner of the affected service.
