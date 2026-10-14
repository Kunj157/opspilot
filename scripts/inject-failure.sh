#!/usr/bin/env bash
# Ships a faulty release of one demo service: a new rollout revision with a
# new version, fault settings, and the release's commit metadata, so
# `kubectl rollout undo` removes it.
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
# A stable, fake commit per release, as a CI build would stamp it.
sha="$(printf '%s %s' "$deployment" "$version" | sha1sum | cut -c1-40)"
env_json="{\"name\":\"SERVICE_VERSION\",\"value\":\"$version\"}"
for assignment in "${envs[@]}"; do
  env_json+=",{\"name\":\"${assignment%%=*}\",\"value\":\"${assignment#*=}\"}"
done
# One patch, so the env and the commit land in the same rollout revision.
$kubectl patch "deployment/$deployment" --type strategic -p "$(cat <<JSON
{"spec":{"template":{"metadata":{"annotations":{
  "opspilot.io/commit-sha":"$sha",
  "opspilot.io/commit-author":"Demo Developer",
  "opspilot.io/commit-message":"$deployment $version: $scenario",
  "opspilot.io/pull-request":""}},
  "spec":{"containers":[{"name":"$deployment","env":[$env_json]}]}}}}
JSON
)"
$kubectl annotate "deployment/$deployment" --overwrite \
  "kubernetes.io/change-cause=release $deployment $version ($scenario)"
$kubectl rollout status "deployment/$deployment" --timeout=2m
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) injected $scenario: $deployment $version ${envs[*]} commit ${sha:0:12}"
