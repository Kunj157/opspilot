#!/usr/bin/env bash
# Backup and restore drill against a disposable database (never production).
#
#   DATABASE_URL=postgresql://.../opspilot_drill READY_URL=http://127.0.0.1:8030/api/v1/ready \
#     scripts/backup-restore-drill.sh
#
# 1. fingerprint the data (row counts + checksums of key tables)
# 2. back up with the chart's own backup.sh (in the server's image)
# 3. write one more incident event (it must be lost: that is the RPO)
# 4. destroy the database
# 5. restore with scripts/restore-db.sh --recreate
# 6. fingerprint again and compare; wait for READY_URL to report ready
# Prints the timings used in docs/operations/backup-restore-drill.md.
set -euo pipefail
cd "$(dirname "$0")/.."

url="$(sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#' <<<"${DATABASE_URL:?}")"
db="$(sed -E 's#^.*/([^/?]+)(\?.*)?$#\1#' <<<"$url")"
[[ "$db" != "opspilot" ]] || { echo "refusing to drill on the main 'opspilot' database" >&2; exit 1; }
PG_IMAGE="${PG_IMAGE:-pgvector/pgvector:0.8.0-pg17}"
out="${BACKUP_DIR:-$(mktemp -d)}"
psql() { docker run --rm -i --network host "$PG_IMAGE" psql "$url" -v ON_ERROR_STOP=1 -Atq "$@"; }
now() { date +%s.%N; }
secs() { awk "BEGIN { printf \"%.1f\", $2 - $1 }"; }

fingerprint() {
  psql <<'SQL'
select 'organizations', count(*), md5(coalesce(string_agg(id::text, ',' order by id), '')) from organizations
union all select 'users', count(*), md5(coalesce(string_agg(id::text || external_auth_id, ',' order by id), '')) from users
union all select 'services', count(*), md5(coalesce(string_agg(id::text || slug, ',' order by id), '')) from services
union all select 'incidents', count(*), md5(coalesce(string_agg(id::text || status::text || version, ',' order by id), '')) from incidents
union all select 'incident_events', count(*), md5(coalesce(string_agg(sequence::text || event_type, ',' order by sequence), '')) from incident_events
union all select 'audit_logs', count(*), md5(coalesce(string_agg(id::text || action, ',' order by id), '')) from audit_logs
union all select 'runbooks', count(*), md5(coalesce(string_agg(id::text || title, ',' order by id), '')) from runbooks
union all select 'runbook_chunks', count(*), md5(coalesce(string_agg(id::text || embedding::text, ',' order by id), '')) from runbook_chunks
union all select 'investigations', count(*), md5(coalesce(string_agg(id::text || status::text, ',' order by id), '')) from investigations
order by 1;
SQL
}

echo "== 1. fingerprint"; fingerprint | tee "$out/before.txt"

echo "== 2. backup"
t0=$(now)
docker run --rm --network host --user "$(id -u):$(id -g)" -e DATABASE_URL="$url" -e BACKUP_DIR=/backup \
  -v "$out:/backup" -v "$PWD/infrastructure/helm/opspilot/files/backup.sh:/backup.sh:ro" \
  "$PG_IMAGE" sh /backup.sh
t1=$(now)
dump="$out/$(cat "$out/LATEST")"
echo "backup took $(secs "$t0" "$t1") s, $(du -h "$dump" | cut -f1)"

echo "== 3. a change after the backup (should be lost)"
psql -c "insert into incident_events (id, organization_id, incident_id, event_type, actor_type, actor_id, title, metadata_json)
  select gen_random_uuid(), organization_id, id, 'incident.note', 'system', 'drill', 'written after the backup', '{}'
  from incidents order by created_at desc limit 1"
lost=$(psql -c "select max(sequence) from incident_events")

echo "== 4. destroy"
t2=$(now)
docker run --rm --network host "$PG_IMAGE" psql "$(sed -E "s#/${db}(\\?.*)?\$#/postgres#" <<<"$url")" -q \
  -c "DROP DATABASE \"$db\" WITH (FORCE)"

echo "== 5. restore"
PG_IMAGE="$PG_IMAGE" scripts/restore-db.sh --recreate "$dump" "$url"
t3=$(now)

echo "== 6. verify"
fingerprint > "$out/after.txt"
diff "$out/before.txt" "$out/after.txt" && echo "fingerprints match"
[[ -z "$(psql -c "select 1 from incident_events where sequence = $lost")" ]] && echo "post-backup event absent (as expected)"
next=$(psql -c "select nextval(pg_get_serial_sequence('incident_events', 'sequence'))")
(( next > lost )) && echo "next event sequence $next > lost $lost: no sequence reuse"
if [[ -n "${READY_URL:-}" ]]; then
  until curl -fsS -m 2 "$READY_URL" >/dev/null 2>&1; do sleep 0.5; done
fi
t4=$(now)
echo "restore took $(secs "$t2" "$t3") s; destroy -> ready (RTO) $(secs "$t2" "$t4") s"
echo "backup finished $(secs "$t1" "$t2") s before the loss (RPO for this drill); files in $out"
