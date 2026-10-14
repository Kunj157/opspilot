# Backup and restore drill

Executed 2026-10-14 against the local compose PostgreSQL (17 + pgvector),
on a disposable database holding the data left by the load tests. Run it
yourself with `scripts/backup-restore-drill.sh` (it refuses the main
`opspilot` database).

## What is backed up, and how

| Data | Where it lives | Backup |
|---|---|---|
| PostgreSQL (users, services, incidents, timeline, audit log, investigations, proposals, approvals, model registry, runbooks **and their embeddings**) | Database | `opspilot-db-backup` CronJob (Helm, `backup.enabled`): `pg_dump --format=custom`, verified with `pg_restore --list`, SHA-256 alongside, to a PVC (14-day retention) or S3-compatible storage |
| Runbook sources | `docs/runbooks/` in git | Git; `make seed-runbooks` reloads them, `POST /api/v1/runbooks/reindex` recomputes embeddings |
| ML model artifacts | `ml/models/*.joblib`, MLflow `ml/mlruns/` (not in git) | Copy both to the backup bucket after each `make ml-train` (`aws s3 sync ml/models s3://<bucket>/opspilot/ml/models`, same for `mlruns`). `model_versions.artifact_uri` points at the file; a missing artifact only disables the shadow scorer (`ModelUnavailable`), detection keeps working |
| Terraform state | S3 backend with versioning (infrastructure/terraform) | Bucket versioning |
| Grafana dashboards, alert rules, chart values | Git (`observability/`, `infrastructure/`) | Git |
| Secrets | External Secrets / AWS Secrets Manager | Provider's own versioning; never in backups |

The job runs as non-root (dump as uid 999, upload as 65534) with read-only
root filesystems. It pushes `opspilot_backup_last_success_timestamp_seconds`
to a Pushgateway when `backup.pushgatewayUrl` is set; without one,
`OpsPilotBackupStale` / `OpsPilotBackupFailed` read the CronJob and Job
status from kube-state-metrics.

## Procedure (as executed)

1. Fingerprint the data: row count and an ordered MD5 per key table.
2. Back up with the chart's own `files/backup.sh`, in the same image the
   CronJob uses (`pgvector/pgvector:0.8.0-pg17`).
3. Write one more timeline event after the backup (it must be lost).
4. Destroy the database (`DROP DATABASE ... WITH (FORCE)`) while the API
   keeps running against it.
5. Restore with `scripts/restore-db.sh --recreate <dump>`: checksum check,
   database recreated, `CREATE EXTENSION vector`, `pg_restore --jobs=4`.
6. Fingerprint again and compare; wait for the running API's `/ready`.

## Results

| Table | Rows | Fingerprint before = after |
|---|---|---|
| organizations | 1 | yes |
| users | 2 | yes |
| services | 5 | yes |
| incidents | 5,437 | yes |
| incident_events | 14,746 | yes |
| audit_logs | 38,510 | yes |
| runbooks / runbook_chunks (with embeddings) | 6 / 54 | yes |
| investigations | 4,492 | yes |

| Measure | Value |
|---|---|
| Dump size (custom format, compression 6) | 4.2 MB |
| Backup duration | 1.1 s |
| Restore duration (recreate + restore) | 4.7 s |
| **RTO measured** (destroy -> API ready again) | **6.8 s** (first run 5.2 s) |
| **RPO measured** | **1.4 s** in the drill (the event written after the backup was lost, as expected) |
| RPO by design | the backup interval: **24 h** with the default nightly schedule (target 24 h) |
| RTO target | 4 h |

The API was not restarted: its pool (pre-ping) and the live-event listener
reconnected by themselves once the database was back, and authenticated
reads and writes worked immediately afterwards.

These numbers are for a small database on a local disk. The restore time
grows roughly with data size; a production-sized database should be timed
again, and the 4 h RTO includes creating the database server itself.

## Problems found

1. **Timeline sequence numbers were reused after a restore.** Events written
   after the backup are lost, but their sequence numbers had already been
   seen by browsers (`Last-Event-ID`) and could have been published. The
   restored identity continued at the old maximum, so the next new event got
   the lost event's number and a reconnecting browser would have skipped it.
   `restore-db.sh` now advances the sequence by 1,000,000 after restoring
   (`SEQUENCE_GAP`); the drill checks it (`next event sequence 1014747 >
   lost 14747`).
2. **`--recreate` needs the extension before the restore** so the dump's
   pgvector columns restore cleanly; the script creates it.
3. **pg_dump must match the server's major version**: the CronJob uses the
   server's own image, and the restore script falls back to it when local
   client tools are missing.
4. Not exercised locally: the S3 upload path (`publish.sh` with
   `S3_BUCKET`), because pulling the AWS CLI image was not worth the disk on
   the shared host; the PVC path and the publish step without upload were
   run. Exercise it once against MinIO or the real bucket before relying on
   it.
