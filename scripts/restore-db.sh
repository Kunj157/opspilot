#!/usr/bin/env bash
# Restore an OpsPilot database from a pg_dump custom-format backup.
#
#   scripts/restore-db.sh [--recreate] <backup.dump | s3://bucket/key.dump> [DATABASE_URL]
#
# The target defaults to $DATABASE_URL (SQLAlchemy or libpq form). With
# --recreate the database is dropped and created again first (it must not be
# in use: stop the API and worker). The checksum next to the dump is verified
# when present. Uses pg_restore/psql from PATH, or the PG_IMAGE container
# (host network) when they are not installed. S3 downloads need the aws CLI
# (S3_ENDPOINT for MinIO and other S3-compatible stores).
# Procedure and measured timings: docs/operations/backup-restore-drill.md.
set -euo pipefail

recreate=false
if [[ "${1:-}" == "--recreate" ]]; then recreate=true; shift; fi
source="${1:?usage: restore-db.sh [--recreate] <backup.dump|s3://...> [DATABASE_URL]}"
url="${2:-${DATABASE_URL:?DATABASE_URL or a second argument is required}}"
url="$(sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#' <<<"$url")"
PG_IMAGE="${PG_IMAGE:-pgvector/pgvector:0.8.0-pg17}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if [[ "$source" == s3://* ]]; then
  endpoint=()
  [[ -n "${S3_ENDPOINT:-}" ]] && endpoint=(--endpoint-url "$S3_ENDPOINT")
  aws "${endpoint[@]}" s3 cp "$source" "$work/" --only-show-errors
  aws "${endpoint[@]}" s3 cp "$source.sha256" "$work/" --only-show-errors || true
  dump="$work/$(basename "$source")"
else
  dump="$(cd "$(dirname "$source")" && pwd)/$(basename "$source")"
fi

if [[ -f "$dump.sha256" ]]; then
  (cd "$(dirname "$dump")" && sha256sum --check --status "$(basename "$dump").sha256") ||
    { echo "checksum mismatch for $dump" >&2; exit 1; }
  echo "checksum ok"
fi

pg() {  # pg <tool> <args...>: local client tools, else the server image
  if command -v "$1" >/dev/null 2>&1; then "$@"; else
    docker run --rm -i --network host -v "$(dirname "$dump"):/dumps:ro" "$PG_IMAGE" "$@"
  fi
}
in_tool_path() { command -v pg_restore >/dev/null 2>&1 && echo "$dump" || echo "/dumps/$(basename "$dump")"; }

if $recreate; then
  db="$(sed -E 's#^.*/([^/?]+)(\?.*)?$#\1#' <<<"$url")"
  admin="$(sed -E "s#/${db}(\\?.*)?\$#/postgres#" <<<"$url")"
  [[ "$db" =~ ^[a-zA-Z0-9_]+$ ]] || { echo "unexpected database name: $db" >&2; exit 1; }
  pg psql "$admin" -v ON_ERROR_STOP=1 -q -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)" -c "CREATE DATABASE \"$db\""
  pg psql "$url" -v ON_ERROR_STOP=1 -q -c "CREATE EXTENSION IF NOT EXISTS vector"
fi

started=$(date +%s)
pg pg_restore --no-owner --no-privileges --exit-on-error --jobs=4 --dbname="$url" "$(in_tool_path)"
# Events written after the backup are lost, but clients and consumers may
# have seen their sequence numbers (SSE Last-Event-ID, relay checkpoints
# elsewhere). Skip ahead so a restored database never reuses one.
pg psql "$url" -v ON_ERROR_STOP=1 -q -c "SELECT setval(pg_get_serial_sequence('incident_events', 'sequence'),
  (SELECT coalesce(max(sequence), 0) + ${SEQUENCE_GAP:-1000000} FROM incident_events))" >/dev/null
echo "restore ok: $(basename "$dump") in $(( $(date +%s) - started )) s"
