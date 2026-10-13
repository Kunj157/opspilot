#!/usr/bin/env bash
# Ships a faulty release of one demo service: a new rollout revision with a
# new version and fault settings, so `kubectl rollout undo` removes it.
set -euo pipefail

scenario="${1:?usage: inject-failure.sh <scenario>}"
catalog="$(dirname "$0")/../demo/failure-injection/scenarios.env"
line="$(grep -E "^${scenario}=" "$catalog" || true)"
if [[ -z "$line" ]]; then
  echo "unknown scenario '$scenario'; known: $(grep -oE '^[a-z0-9-]+' "$catalog" | tr '\n' ' ')" >&2
  exit 2
fi
IFS='|' read -r deployment version settings <<<"${line#*=}"

kubectl="kubectl --context kind-opspilot -n demo"
read -r -a envs <<<"$settings"
$kubectl set env "deployment/$deployment" "SERVICE_VERSION=$version" "${envs[@]}"
$kubectl annotate "deployment/$deployment" --overwrite \
  "kubernetes.io/change-cause=release $deployment $version ($scenario)"
$kubectl rollout status "deployment/$deployment" --timeout=2m
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) injected $scenario: $deployment $version ${envs[*]}"
