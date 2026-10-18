"""Add application, scheduling and compute governance tables."""
from alembic import op

revision = "20261018_platform_plus"
down_revision = "20261018_canary"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS workflow_schedules (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      workflow_id varchar(36) NOT NULL REFERENCES workflows(id),
      environment varchar(40) NOT NULL DEFAULT 'production',
      interval_seconds integer NOT NULL,
      next_run_at timestamptz NOT NULL,
      last_run_at timestamptz NULL,
      input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      active boolean NOT NULL DEFAULT true,
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_schedules_next_run_at ON workflow_schedules(next_run_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_schedules_active ON workflow_schedules(active)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS applications (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      project_id varchar(36) NOT NULL REFERENCES projects(id),
      name varchar(160) NOT NULL,
      slug varchar(100) NOT NULL,
      description text NOT NULL DEFAULT '',
      app_type varchar(30) NOT NULL DEFAULT 'low_code',
      status varchar(30) NOT NULL DEFAULT 'draft',
      runtime_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_application_scope_slug UNIQUE (tenant_id, project_id, slug)
    )
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS application_versions (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      application_id varchar(36) NOT NULL REFERENCES applications(id),
      version integer NOT NULL,
      source_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      status varchar(30) NOT NULL DEFAULT 'draft',
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_application_version UNIQUE (application_id, version)
    )
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS compute_quotas (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      cpu_millicores integer NOT NULL DEFAULT 2000,
      memory_mb integer NOT NULL DEFAULT 4096,
      gpu_count integer NOT NULL DEFAULT 0,
      concurrent_runs integer NOT NULL DEFAULT 10,
      monthly_tokens integer NOT NULL DEFAULT 1000000,
      enabled boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_compute_quota_tenant UNIQUE (tenant_id)
    )
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS compute_usage (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      run_id varchar(36) NULL REFERENCES workflow_runs(id),
      cpu_milliseconds integer NOT NULL DEFAULT 0,
      memory_mb_seconds integer NOT NULL DEFAULT 0,
      gpu_seconds integer NOT NULL DEFAULT 0,
      tokens integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS compute_usage")
    op.execute("DROP TABLE IF EXISTS compute_quotas")
    op.execute("DROP TABLE IF EXISTS application_versions")
    op.execute("DROP TABLE IF EXISTS applications")
    op.execute("DROP TABLE IF EXISTS workflow_schedules")
