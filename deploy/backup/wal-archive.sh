#!/usr/bin/env bash
set -Eeuo pipefail

# PostgreSQL archive_command passes the WAL file path as $1 and the file name as $2.
# The command must be idempotent: PostgreSQL can retry the same segment after a
# transient upload failure.
: "${WAL_ARCHIVE_URI:?set WAL_ARCHIVE_URI, for example s3://bucket/platform-wal}"
wal_path="${1:?missing WAL file path}"
wal_name="${2:?missing WAL file name}"

if [[ ! -f "$wal_path" ]]; then
  printf 'WAL file does not exist: %s\n' "$wal_path" >&2
  exit 1
fi
if [[ ! "$wal_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf 'unsafe WAL file name: %s\n' "$wal_name" >&2
  exit 2
fi

case "$WAL_ARCHIVE_URI" in
  s3://*)
    command -v aws >/dev/null 2>&1 || {
      printf 'aws CLI is required for S3 WAL archiving\n' >&2
      exit 3
    }
    aws s3 cp "$wal_path" "${WAL_ARCHIVE_URI%/}/$wal_name" --only-show-errors
    ;;
  file://*)
    target="${WAL_ARCHIVE_URI#file://}/$wal_name"
    mkdir -p "$(dirname "$target")"
    cp -- "$wal_path" "$target"
    ;;
  *)
    printf 'unsupported WAL_ARCHIVE_URI: %s\n' "$WAL_ARCHIVE_URI" >&2
    exit 2
    ;;
esac
