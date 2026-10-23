# PostgreSQL WAL/PITR deployment

The repository now contains two supported deployment paths:

* Local or isolated rehearsal: run the normal Compose file together with
  `docker-compose.pitr.yml`. The override starts PostgreSQL with
  `wal_level=replica`, `archive_mode=on`, a 60-second `archive_timeout`, and
  the repository's `archive_command`.
* Kubernetes: use a PostgreSQL operator. The CloudNativePG example declares a
  Barman object store, which is the component responsible for continuous WAL
  archiving and base backups.

For a local rehearsal:

```powershell
$env:WAL_ARCHIVE_URI = 'file:///var/lib/postgresql/wal-archive'
docker compose -f docker-compose.yml -f docker-compose.pitr.yml up -d postgres
docker compose -f docker-compose.yml -f docker-compose.pitr.yml exec -e PITR_DATABASE_URL=postgresql://platform:REPLACE_PASSWORD@127.0.0.1:5432/platform postgres /usr/local/bin/pitr-check.sh
```

The check script is mounted into a backup/operations image in production:

```bash
PITR_DATABASE_URL=postgresql://... deploy/backup/pitr-check.sh
```

For production, set `WAL_ARCHIVE_URI` to a separate durable S3-compatible
bucket and provide the PostgreSQL process with credentials through its secret
mechanism. Do not use the same volume as the primary data directory as the
durable recovery target. `deploy/backup/backup.sh` remains the periodic base
backup, while the WAL archive closes the gap between base backups.

Before declaring disaster recovery accepted, run `deploy/backup/dr-test.sh`
against a customer-like PostgreSQL/WAL environment and record the observed
RPO/RTO. Static configuration and Compose validation do not replace that
exercise.

CI runs `deploy/ci/pitr-smoke.sh`, which starts the PITR Compose override,
executes `pg_switch_wal()`, and waits for `pg_stat_archiver.archived_count` to
increase. This proves the local archive command is wired correctly; it does
not prove S3 credentials, retention, or a customer environment's restore RPO.
