#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_PASSWORD:?缺少 POSTGRES_PASSWORD}"
: "${POSTGRES_RUNTIME_PASSWORD:?缺少 POSTGRES_RUNTIME_PASSWORD}"

tenant_slug="ci-rls-$(date +%s)"
tenant_id="ci-rls-id-$(date +%s)"
cleanup() {
  docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U platform -d platform \
    --command="DELETE FROM tenants WHERE id = '$tenant_id'" >/dev/null 2>&1 || true
}
trap cleanup EXIT

tenant_a="$(docker compose exec -T postgres psql -U platform -d platform --tuples-only --no-align \
  --command="SELECT id FROM tenants WHERE slug = 'acme' LIMIT 1" | tr -d '\r' | tr -d '[:space:]')"
test -n "$tenant_a"
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U platform -d platform \
  --command="INSERT INTO tenants (id, name, slug, is_active) VALUES ('$tenant_id', 'CI RLS Tenant', '$tenant_slug', true)"

count_a="$(docker compose exec -T -e "PGPASSWORD=$POSTGRES_RUNTIME_PASSWORD" postgres psql -U platform_runtime -d platform --tuples-only --no-align \
  --command="SELECT set_config('app.tenant_id', '$tenant_a', true); SELECT count(*) FROM tenants" | tail -n 1 | tr -d '\r' | tr -d '[:space:]')"
count_b="$(docker compose exec -T -e "PGPASSWORD=$POSTGRES_RUNTIME_PASSWORD" postgres psql -U platform_runtime -d platform --tuples-only --no-align \
  --command="SELECT set_config('app.tenant_id', '$tenant_id', true); SELECT count(*) FROM tenants" | tail -n 1 | tr -d '\r' | tr -d '[:space:]')"

test "$count_a" = "1"
test "$count_b" = "1"
printf 'PostgreSQL RLS 跨租户冒烟测试通过\n'
