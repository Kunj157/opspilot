#!/usr/bin/env bash
# Print an access token for a local Keycloak dev user (dev/test only).
set -euo pipefail
user="${1:?usage: dev-token.sh <viewer|operator|commander|admin|outsider>}"
base="http://localhost:${KEYCLOAK_PORT:-8080}/realms/opspilot"
curl -fsS "$base/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=opspilot-dev-cli \
  -d username="$user" -d password=opspilot-dev \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
