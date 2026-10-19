"""Add idempotent workflow run creation and retry lineage."""
from alembic import op

revision = "20261020_workflow_reliability"
down_revision = "20261019_finops_observability"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS idempotency_key varchar(120) NULL")
    op.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS retry_of_id varchar(36) NULL REFERENCES workflow_runs(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_runs_retry_of_id ON workflow_runs(retry_of_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_run_idempotency ON workflow_runs(tenant_id, workflow_id, created_by, idempotency_key)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS model_conversations (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      user_id varchar(36) NOT NULL REFERENCES users(id),
      provider_id varchar(36) NOT NULL REFERENCES model_providers(id),
      title varchar(160) NOT NULL DEFAULT '新会话',
      messages_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_model_conversations_tenant_id ON model_conversations(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_model_conversations_user_id ON model_conversations(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_model_conversations_provider_id ON model_conversations(provider_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS model_conversations")
    op.execute("DROP INDEX IF EXISTS uq_workflow_run_idempotency")
    op.execute("DROP INDEX IF EXISTS ix_workflow_runs_retry_of_id")
    op.execute("ALTER TABLE workflow_runs DROP COLUMN IF EXISTS retry_of_id")
    op.execute("ALTER TABLE workflow_runs DROP COLUMN IF EXISTS idempotency_key")
