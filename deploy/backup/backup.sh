#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_DATABASE_URL:?必须设置 BACKUP_DATABASE_URL（标准 postgresql:// 地址）}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
ARTIFACT_DIR="${ARTIFACT_DIR:-/artifacts}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
umask 077
mkdir -p "$BACKUP_DIR"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$BACKUP_DIR/enterprise-ai-$stamp.tar.gz"

pg_dump --dbname="$BACKUP_DATABASE_URL" --format=custom --no-owner --file="$work_dir/database.dump"
if [[ -d "$ARTIFACT_DIR" ]]; then
  tar -C "$ARTIFACT_DIR" -czf "$work_dir/artifacts.tar.gz" .
else
  tar -czf "$work_dir/artifacts.tar.gz" --files-from /dev/null
fi
printf 'created_at=%s\ndatabase_format=pg_custom\nartifacts_included=true\n' "$stamp" > "$work_dir/metadata.txt"
(cd "$work_dir" && sha256sum database.dump artifacts.tar.gz metadata.txt > checksums.sha256)
tar -C "$work_dir" -czf "$archive" database.dump artifacts.tar.gz metadata.txt checksums.sha256

upload_file="$archive"
if [[ -n "${BACKUP_AGE_RECIPIENT:-}" ]]; then
  age --recipient "$BACKUP_AGE_RECIPIENT" --output "$archive.age" "$archive"
  rm -f -- "$archive"
  upload_file="$archive.age"
fi
if [[ -n "${BACKUP_S3_URI:-}" ]]; then
  aws s3 cp "$upload_file" "${BACKUP_S3_URI%/}/$(basename "$upload_file")" --only-show-errors
fi
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'enterprise-ai-*' -mtime "+$BACKUP_RETENTION_DAYS" -delete
printf '备份完成: %s\n' "$upload_file"
