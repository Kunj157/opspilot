#!/usr/bin/env bash
# Verifies the local realm: each dev user's access token carries the expected
# issuer, audience, organization, and realm role.
set -euo pipefail
cd "$(dirname "$0")/.."
issuer="http://localhost:${KEYCLOAK_PORT:-8080}/realms/opspilot"
fail=0
while read -r user org role; do
  token="$(./scripts/dev-token.sh "$user")"
  if python3 - "$token" "$issuer" "$org" "$role" <<'PY'
import base64, json, sys
token, issuer, org, role = sys.argv[1:]
payload = token.split(".")[1]
claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
aud = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
problems = []
if claims["iss"] != issuer: problems.append(f"iss={claims['iss']}")
if "opspilot-api" not in aud: problems.append(f"aud={aud}")
if claims.get("organization") != org: problems.append(f"organization={claims.get('organization')}")
if role not in claims.get("realm_access", {}).get("roles", []): problems.append("missing role")
print(("ok   " if not problems else "FAIL ") + sys.argv[3] + "/" + role + (" " + ", ".join(problems) if problems else ""))
sys.exit(1 if problems else 0)
PY
  then :; else fail=1; fi
done <<'USERS'
viewer acme viewer
operator acme operator
commander acme incident-commander
admin acme administrator
outsider globex administrator
USERS
exit "$fail"
