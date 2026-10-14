# Disaster recovery runbook

Targets (portfolio demonstration, not an enterprise commitment): **RPO 24 h,
RTO 4 h**. Last drill: [backup-restore-drill.md](backup-restore-drill.md)
(measured RTO 6.8 s for the database step, RPO = backup interval).

## Decide what happened

| Situation | Go to |
|---|---|
| Bad migration or bad data written by a release | [Restore the database](#restore-the-database) into a new database, compare, then switch |
| Database server lost (managed instance deleted, volume corrupt) | [Rebuild the environment](#rebuild-the-environment) then restore |
| One table damaged, rest healthy | Restore the dump into a scratch database and copy the rows back (`pg_restore --table=...`); never overwrite the live database first |
| Cluster lost, database fine | Recreate the cluster (Terraform), deploy (Argo CD); no restore needed |

Before anything else: stop writers so the damage does not spread.

```bash
kubectl -n opspilot scale deploy/opspilot-worker --replicas=0
kubectl -n opspilot scale deploy/opspilot-api --replicas=0   # if the data is being corrupted
```

## Find the backup

- PVC destination: `kubectl -n opspilot run restore-shell --rm -it --image=pgvector/pgvector:0.8.0-pg17
  --overrides='<mount the opspilot-db-backup claim>' -- ls -l /backup` (`LATEST` names the newest dump).
- S3 destination: `aws s3 ls s3://<bucket>/opspilot/postgres/ | tail` (each `.dump` has a `.sha256`).
- Pick the newest dump **before** the incident started; note its timestamp:
  everything after it is lost (that is the RPO actually incurred).

## Restore the database

```bash
# Into a fresh database first (safe), from a workstation or a pod with network access:
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/opspilot_restore \
  scripts/restore-db.sh --recreate s3://<bucket>/opspilot/postgres/opspilot-<stamp>.dump
```

The script verifies the checksum, recreates the database with the pgvector
extension, restores with four parallel jobs, and advances the timeline
sequence past anything clients may have seen. Then:

1. Check the data: row counts of `incidents`, `incident_events`,
   `audit_logs`, `users`, `services`, `runbooks` look right; the newest
   incident is the one you expect.
2. Point the application at it: update `DATABASE_URL` in the secret
   (External Secrets: in Secrets Manager), or rename databases
   (`ALTER DATABASE opspilot RENAME TO opspilot_broken; ALTER DATABASE
   opspilot_restore RENAME TO opspilot;` with no connections).
3. Run migrations if the restored schema is older than the release:
   the `opspilot-migrate` Job does this on deploy.
4. Scale the API and worker back up; `/api/v1/ready` must report `ready`.

## Rebuild the environment

1. Infrastructure: `cd infrastructure/terraform/environments/<env> && terraform apply`
   (state is in the versioned S3 backend).
2. Secrets: restored by External Secrets from Secrets Manager.
3. Application: Argo CD syncs the chart from git; with an empty database the
   migrate Job creates the schema, then restore over it with `--recreate`.
4. ML model artifacts: `aws s3 sync s3://<bucket>/opspilot/ml/models ml/models`
   on whatever serves the shadow scorer (missing artifacts only disable it).
5. Runbooks: already in the database dump; if not, `make seed-runbooks` and
   `POST /api/v1/runbooks/reindex`.

## After the restore

- Tell users which window of data was lost (from the dump time to the incident).
- Live browsers reconnect by themselves; consumers deduplicate replayed events
  by event ID, and the outbox relay resumes from the restored checkpoint
  (it may republish events consumers already handled; that is safe).
- Investigations that were running are re-claimed when their leases expire.
- Check `OpsPilotBackupStale` clears after the next scheduled backup, and run
  one now: `kubectl -n opspilot create job --from=cronjob/opspilot-db-backup backup-after-restore`.
- Write a postmortem; add anything that surprised you to this runbook.

## Practise

Run `scripts/backup-restore-drill.sh` against a disposable database at least
once per release and after any change to the schema size or backup job;
update the drill document with the numbers.
