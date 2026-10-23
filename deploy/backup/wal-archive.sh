#!/usr/bin/env bash
set -Eeuo pipefail

# PostgreSQL archive_command passes the WAL file path as $1 and file name as $2.
: "${WAL_ARCHIVE_URI:?必须设置 WAL_ARCHIVE_URI，例如 s3://bucket/platform-wal}"
wal_path="${1:?缺少 WAL 文件路径}"
wal_name="${2:?缺少 WAL 文件名}"

case "$WAL_ARCHIVE_URI" in
  s3://*)
    aws s3 cp "$wal_path" "${WAL_ARCHIVE_URI%/}/$wal_name" --only-show-errors
    ;;
  file://*)
    target="${WAL_ARCHIVE_URI#file://}/$wal_name"
    mkdir -p "$(dirname "$target")"
    cp -- "$wal_path" "$target"
    ;;
  *)
    printf '不支持的 WAL_ARCHIVE_URI: %s\n' "$WAL_ARCHIVE_URI" >&2
    exit 2
    ;;
esac
