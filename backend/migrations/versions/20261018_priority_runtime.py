"""Add priority runtime, GPU leasing, sandbox, async evaluation and plugin approval."""
from alembic import op

revision = "20261018_priority_runtime"
down_revision = "20261018_priority_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE plugins ADD COLUMN IF NOT EXISTS approval_status varchar(30) NOT NULL DEFAULT 'pending'")
    op.execute("ALTER TABLE plugins ADD COLUMN IF NOT EXISTS approved_by varchar(36) NULL REFERENCES users(id)")
    op.execute("ALTER TABLE plugins ADD COLUMN IF NOT EXISTS approved_at timestamptz NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_plugins_approval_status ON plugins(approval_status)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS gpu_leases (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      run_id varchar(36) NULL REFERENCES workflow_runs(id),
      requested_count integer NOT NULL DEFAULT 1,
      status varchar(30) NOT NULL DEFAULT 'queued',
      node_name varchar(160) NOT NULL DEFAULT '',
      expires_at timestamptz NOT NULL,
      released_at timestamptz NULL,
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_gpu_leases_status ON gpu_leases(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_gpu_leases_expires_at ON gpu_leases(expires_at)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS sandbox_runs (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      application_id varchar(36) NULL REFERENCES applications(id),
      status varchar(30) NOT NULL DEFAULT 'queued',
      runtime varchar(30) NOT NULL DEFAULT 'nodejs',
      source_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      output_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      error text NOT NULL DEFAULT '',
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      started_at timestamptz NULL,
      finished_at timestamptz NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sandbox_runs_status ON sandbox_runs(status)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS evaluation_jobs (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      agent_id varchar(36) NOT NULL REFERENCES agents(id),
      status varchar(30) NOT NULL DEFAULT 'queued',
      request_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      results_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      error text NOT NULL DEFAULT '',
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      started_at timestamptz NULL,
      finished_at timestamptz NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_evaluation_jobs_status ON evaluation_jobs(status)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS evaluation_jobs")
    op.execute("DROP TABLE IF EXISTS sandbox_runs")
    op.execute("DROP TABLE IF EXISTS gpu_leases")
    op.execute("ALTER TABLE plugins DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE plugins DROP COLUMN IF EXISTS approved_by")
    op.execute("ALTER TABLE plugins DROP COLUMN IF EXISTS approval_status")
