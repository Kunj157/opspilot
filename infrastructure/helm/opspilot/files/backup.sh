#!/bin/sh
# OpsPilot database backup: pg_dump (custom format) + SHA-256, verified with
# pg_restore --list, written to BACKUP_DIR; old dumps pruned after
# RETENTION_DAYS. publish.sh then uploads it (S3) and reports success.
#
#   DATABASE_URL       SQLAlchemy or libpq URL of the database
#   BACKUP_DIR         where the dump goes (PVC mount, or a staging dir for S3)
#   RETENTION_DAYS     local dumps older than this are deleted (0 = keep all)
#
# Used by the opspilot-db-backup CronJob and by the restore drill
# (docs/operations/backup-restore-drill.md); restore with scripts/restore-db.sh.
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_DIR="${BACKUP_DIR:-/backup}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
url=$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+[a-z0-9]*://#postgresql://#')
stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="opspilot-${stamp}.dump"
started=$(date +%s)

mkdir -p "$BACKUP_DIR"
pg_dump --format=custom --compress=6 --no-owner --no-privileges \
  --file="$BACKUP_DIR/$name.partial" --dbname="$url"
# A dump pg_restore cannot list is not a backup.
pg_restore --list "$BACKUP_DIR/$name.partial" > /dev/null
mv "$BACKUP_DIR/$name.partial" "$BACKUP_DIR/$name"
(cd "$BACKUP_DIR" && sha256sum "$name" > "$name.sha256")

if [ "$RETENTION_DAYS" -gt 0 ]; then
  find "$BACKUP_DIR" -maxdepth 1 -name 'opspilot-*.dump*' -mtime "+$RETENTION_DAYS" -delete
fi

size=$(wc -c < "$BACKUP_DIR/$name")
echo "backup ok: $name ($size bytes) in $(( $(date +%s) - started )) s"
echo "$name" > "$BACKUP_DIR/LATEST"

