#!/bin/sh
# Second step of the backup Job: upload the dump named in $BACKUP_DIR/LATEST
# to S3-compatible storage (when S3_BUCKET is set), then push the success
# time to a Pushgateway (when PUSHGATEWAY_URL is set). Without either it
# only confirms the dump exists; kube-state-metrics still sees the Job.
#
#   S3_BUCKET, S3_PREFIX (default opspilot/postgres), S3_ENDPOINT (MinIO etc.)
#   Credentials: IRSA / instance role, or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backup}"
name=$(cat "$BACKUP_DIR/LATEST")
test -s "$BACKUP_DIR/$name"

if [ -n "${S3_BUCKET:-}" ]; then
  target="s3://$S3_BUCKET/${S3_PREFIX:-opspilot/postgres}"
  endpoint=""
  if [ -n "${S3_ENDPOINT:-}" ]; then endpoint="--endpoint-url $S3_ENDPOINT"; fi
  # shellcheck disable=SC2086 # endpoint is either empty or two words
  aws $endpoint s3 cp "$BACKUP_DIR/$name" "$target/$name" --only-show-errors
  # shellcheck disable=SC2086
  aws $endpoint s3 cp "$BACKUP_DIR/$name.sha256" "$target/$name.sha256" --only-show-errors
  echo "uploaded $name to $target"
fi

if [ -n "${PUSHGATEWAY_URL:-}" ]; then
  size=$(wc -c < "$BACKUP_DIR/$name")
  printf 'opspilot_backup_last_success_timestamp_seconds %s\nopspilot_backup_size_bytes %s\n' \
    "$(date +%s)" "$size" |
    curl -fsS --max-time 10 --data-binary @- "$PUSHGATEWAY_URL/metrics/job/opspilot-db-backup" ||
    echo "warning: could not push the backup metric"
fi
echo "backup published: $name"
