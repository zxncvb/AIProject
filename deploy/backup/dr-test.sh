#!/usr/bin/env bash
set -Eeuo pipefail

: "${DR_ARCHIVE:?必须设置 DR_ARCHIVE}"
container="enterprise-ai-dr-$RANDOM-$$"
volume="enterprise-ai-dr-artifacts-$RANDOM-$$"
started="$(date +%s)"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker run -d --name "$container" -e POSTGRES_PASSWORD=dr-test-password -e POSTGRES_DB=platform postgres:16-alpine >/dev/null
for _ in $(seq 1 60); do
  if docker exec "$container" pg_isready -U postgres -d platform >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec "$container" pg_isready -U postgres -d platform >/dev/null
docker run --rm --network "container:$container" -e RESTORE_DATABASE_URL=postgresql://postgres:dr-test-password@127.0.0.1:5432/platform -e RESTORE_ARCHIVE=/backup/$(basename "$DR_ARCHIVE") -e RESTORE_CONFIRM=RESTORE -e ARTIFACT_DIR=/artifacts -v "$(cd "$(dirname "$DR_ARCHIVE")" && pwd):/backup:ro" -v "$volume:/artifacts" --entrypoint /usr/local/bin/restore.sh enterprise-ai-platform/backup:latest
docker exec "$container" psql -U postgres -d platform --no-psqlrc --tuples-only --command='SELECT count(*) FROM tenants' >/dev/null
elapsed="$(( $(date +%s) - started ))"
printf '隔离灾备演练通过，RTO=%s 秒，生产环境未被修改\n' "$elapsed"
