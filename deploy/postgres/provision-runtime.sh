#!/bin/sh
set -eu

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_RUNTIME_PASSWORD:?POSTGRES_RUNTIME_PASSWORD is required}"
: "${POSTGRES_CONTROLLER_PASSWORD:?POSTGRES_CONTROLLER_PASSWORD is required}"

export PGPASSWORD="$POSTGRES_PASSWORD"
psql --host="${POSTGRES_HOST:-postgres}" --username="${POSTGRES_USER:-platform}" --dbname="${POSTGRES_DB:-platform}" \
  --set=ON_ERROR_STOP=1 \
  --set=runtime_password="$POSTGRES_RUNTIME_PASSWORD" \
  --set=controller_password="$POSTGRES_CONTROLLER_PASSWORD" \
  --set=admin_role="${POSTGRES_USER:-platform}" <<'SQL'
SELECT format('CREATE ROLE platform_runtime LOGIN PASSWORD %L', :'runtime_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_runtime') \gexec
ALTER ROLE platform_runtime PASSWORD :'runtime_password' NOSUPERUSER NOBYPASSRLS;
SELECT format('CREATE ROLE platform_controller LOGIN PASSWORD %L NOSUPERUSER BYPASSRLS', :'controller_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_controller') \gexec
ALTER ROLE platform_controller PASSWORD :'controller_password' NOSUPERUSER BYPASSRLS;
GRANT CONNECT ON DATABASE platform TO platform_runtime;
GRANT USAGE ON SCHEMA public TO platform_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO platform_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO platform_runtime;
GRANT CONNECT ON DATABASE platform TO platform_controller;
GRANT USAGE ON SCHEMA public TO platform_controller;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO platform_controller;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO platform_controller;
ALTER DEFAULT PRIVILEGES FOR ROLE :"admin_role" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO platform_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE :"admin_role" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO platform_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE :"admin_role" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO platform_controller;
ALTER DEFAULT PRIVILEGES FOR ROLE :"admin_role" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO platform_controller;
SQL

psql --host="${POSTGRES_HOST:-postgres}" --username="${POSTGRES_USER:-platform}" --dbname="${POSTGRES_DB:-platform}" \
  --set=ON_ERROR_STOP=1 --file=/security/rls.sql
