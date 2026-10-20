"""Production completion: content security, application runtime and governance."""
from alembic import op


revision = "20261021_enterprise_completion"
down_revision = "20261020_rls_enforcement"
branch_labels = None
depends_on = None


NEW_TENANT_TABLES = (
    "application_builds", "application_deployments", "publish_deliveries",
    "approval_policies", "approval_votes",
)


def _tenant_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.execute(
        f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))'''
    )


def upgrade():
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS mime_type varchar(160) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_size integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_method varchar(30) NOT NULL DEFAULT 'parser'")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS security_status varchar(30) NOT NULL DEFAULT 'clean'")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS security_report_json jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_security_status ON documents(security_status)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS application_builds (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      application_id varchar(36) NOT NULL REFERENCES applications(id),
      version integer NOT NULL,
      status varchar(30) NOT NULL DEFAULT 'queued',
      image varchar(500) NOT NULL DEFAULT '',
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
    op.execute("CREATE INDEX IF NOT EXISTS ix_application_builds_tenant_id ON application_builds(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_application_builds_application_id ON application_builds(application_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_application_builds_status ON application_builds(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_application_builds_created_at ON application_builds(created_at)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS application_deployments (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      application_id varchar(36) NOT NULL REFERENCES applications(id),
      build_id varchar(36) NULL REFERENCES application_builds(id),
      version integer NOT NULL,
      revision integer NOT NULL,
      environment varchar(40) NOT NULL DEFAULT 'production',
      status varchar(30) NOT NULL DEFAULT 'queued',
      image varchar(500) NOT NULL,
      replicas integer NOT NULL DEFAULT 1,
      endpoint_url varchar(800) NOT NULL DEFAULT '',
      manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      error text NOT NULL DEFAULT '',
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_application_deployment_revision UNIQUE(application_id, environment, revision)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_application_deployments_tenant_id ON application_deployments(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_application_deployments_application_id ON application_deployments(application_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_application_deployments_build_id ON application_deployments(build_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_application_deployments_status ON application_deployments(status)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS publish_deliveries (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      binding_id varchar(36) NOT NULL REFERENCES publish_bindings(id),
      status varchar(30) NOT NULL DEFAULT 'queued',
      attempt_count integer NOT NULL DEFAULT 0,
      payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      response_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      error text NOT NULL DEFAULT '',
      next_attempt_at timestamptz NULL,
      delivered_at timestamptz NULL,
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_publish_deliveries_tenant_id ON publish_deliveries(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_publish_deliveries_binding_id ON publish_deliveries(binding_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_publish_deliveries_status ON publish_deliveries(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_publish_deliveries_next_attempt_at ON publish_deliveries(next_attempt_at)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS approval_policies (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      name varchar(160) NOT NULL,
      request_type varchar(80) NOT NULL,
      resource_type varchar(40) NOT NULL DEFAULT '',
      approver_roles_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      conditions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      min_approvals integer NOT NULL DEFAULT 1,
      allow_self_approval boolean NOT NULL DEFAULT false,
      expires_in_minutes integer NOT NULL DEFAULT 1440,
      enabled boolean NOT NULL DEFAULT true,
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_approval_policy_name UNIQUE(tenant_id, name)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_policies_tenant_id ON approval_policies(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_policies_request_type ON approval_policies(request_type)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS approval_votes (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      request_id varchar(36) NOT NULL REFERENCES approval_requests(id),
      approver_id varchar(36) NOT NULL REFERENCES users(id),
      approved boolean NOT NULL,
      comment text NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_approval_vote_approver UNIQUE(request_id, approver_id)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_votes_tenant_id ON approval_votes(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_votes_request_id ON approval_votes(request_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_votes_approver_id ON approval_votes(approver_id)")

    for table in NEW_TENANT_TABLES:
        _tenant_rls(table)
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON application_builds, application_deployments,
          publish_deliveries, approval_policies, approval_votes TO platform_runtime;
      END IF;
    END $$
    """)


def downgrade():
    for table in reversed(NEW_TENANT_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    op.execute("DROP INDEX IF EXISTS ix_documents_security_status")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS security_report_json")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS security_status")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS extraction_method")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS file_size")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS mime_type")
