#!/usr/bin/env bash
set -Eeuo pipefail

: "${PITR_DATABASE_URL:?set PITR_DATABASE_URL}"

row="$(psql "$PITR_DATABASE_URL" --no-psqlrc --tuples-only --no-align --command \
  "SELECT current_setting('wal_level'), current_setting('archive_mode'), current_setting('archive_command')")"
IFS='|' read -r wal_level archive_mode archive_command <<< "$row"

[[ "$wal_level" == "replica" || "$wal_level" == "logical" ]] || {
  printf 'invalid wal_level: %s\n' "$wal_level" >&2
  exit 1
}
[[ "$archive_mode" == "on" ]] || {
  printf 'archive_mode is not on\n' >&2
  exit 1
}
[[ "$archive_command" != '(disabled)' && "$archive_command" != "" ]] || {
  printf 'archive_command is disabled\n' >&2
  exit 1
}

printf 'PITR configuration is enabled: wal_level=%s archive_mode=%s archive_command=%s\n' \
  "$wal_level" "$archive_mode" "$archive_command"
