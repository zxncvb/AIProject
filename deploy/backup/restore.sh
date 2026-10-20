#!/usr/bin/env bash
set -Eeuo pipefail

: "${RESTORE_DATABASE_URL:?必须设置 RESTORE_DATABASE_URL}"
: "${RESTORE_ARCHIVE:?必须设置 RESTORE_ARCHIVE}"
if [[ "${RESTORE_CONFIRM:-}" != "RESTORE" ]]; then
  printf '拒绝恢复：请显式设置 RESTORE_CONFIRM=RESTORE\n' >&2
  exit 2
fi
ARTIFACT_DIR="${ARTIFACT_DIR:-/artifacts}"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
archive="$RESTORE_ARCHIVE"
if [[ "$archive" == *.age ]]; then
  : "${RESTORE_AGE_IDENTITY:?加密备份必须设置 RESTORE_AGE_IDENTITY}"
  age --decrypt --identity "$RESTORE_AGE_IDENTITY" --output "$work_dir/archive.tar.gz" "$archive"
  archive="$work_dir/archive.tar.gz"
fi
tar -xzf "$archive" -C "$work_dir"
(cd "$work_dir" && sha256sum --check checksums.sha256)
pg_restore --dbname="$RESTORE_DATABASE_URL" --clean --if-exists --no-owner --exit-on-error "$work_dir/database.dump"
mkdir -p "$ARTIFACT_DIR"
find "$ARTIFACT_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
tar -xzf "$work_dir/artifacts.tar.gz" -C "$ARTIFACT_DIR"
psql "$RESTORE_DATABASE_URL" --no-psqlrc --tuples-only --command='SELECT 1' >/dev/null
printf '恢复及校验完成\n'
