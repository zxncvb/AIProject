-- Run as the PostgreSQL owner after replacing the password below.
-- The API must use DATABASE_URL with platform_runtime and
-- DATABASE_ADMIN_URL with platform for bootstrap/auth/worker operations.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_runtime') THEN
    CREATE ROLE platform_runtime LOGIN PASSWORD 'REPLACE_WITH_RUNTIME_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END $$;
GRANT CONNECT ON DATABASE platform TO platform_runtime;
GRANT USAGE ON SCHEMA public TO platform_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO platform_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO platform_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE platform IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO platform_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE platform IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO platform_runtime;
-- Apply deploy/postgres/rls.sql in a second psql invocation when using stdin.
