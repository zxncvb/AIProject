#!/usr/bin/env bash
set -Eeuo pipefail

project="${COMPOSE_PROJECT_NAME:-enterprise-ai-pitr-smoke}"
compose=(docker compose -p "$project" -f docker-compose.yml -f docker-compose.pitr.yml)
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pitr-smoke-password}"
export POSTGRES_RUNTIME_PASSWORD="${POSTGRES_RUNTIME_PASSWORD:-pitr-runtime-password}"
export POSTGRES_CONTROLLER_PASSWORD="${POSTGRES_CONTROLLER_PASSWORD:-pitr-controller-password}"
export GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-pitr-grafana-password}"
export WAL_ARCHIVE_URI="${WAL_ARCHIVE_URI:-file:///var/lib/postgresql/wal-archive}"

cleanup() {
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${compose[@]}" up -d --build postgres
for attempt in $(seq 1 60); do
  if "${compose[@]}" exec -T postgres pg_isready -U platform -d platform >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == 60 ]]; then
    echo 'PostgreSQL did not become ready' >&2
    exit 1
  fi
  sleep 1
done

database_url="postgresql://platform:${POSTGRES_PASSWORD}@127.0.0.1:5432/platform"
"${compose[@]}" exec -T -e "PITR_DATABASE_URL=$database_url" postgres /usr/local/bin/pitr-check.sh
"${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U platform -d platform \
  --no-psqlrc --command='SELECT pg_switch_wal()' >/dev/null

for attempt in $(seq 1 90); do
  archived_count="$("${compose[@]}" exec -T postgres psql -U platform -d platform --tuples-only --no-align \
    --no-psqlrc --command="SELECT archived_count FROM pg_stat_archiver")"
  archived_count="$(echo "$archived_count" | tr -d '[:space:]')"
  if [[ "$archived_count" =~ ^[0-9]+$ ]] && (( archived_count > 0 )); then
    echo "PITR WAL archive smoke test passed: archived_count=$archived_count"
    exit 0
  fi
  sleep 1
done

echo 'PostgreSQL did not archive a WAL segment within 90 seconds' >&2
"${compose[@]}" logs --no-color postgres >&2 || true
exit 1
