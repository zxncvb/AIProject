"""Add tenant policies for safety and FinOps."""
from alembic import op

revision = "20261018_enterprise_pack"
down_revision = "20261018_production_pack"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS tenant_policies (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      safety_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      pricing_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_tenant_policy_tenant UNIQUE (tenant_id)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_tenant_policies_tenant_id ON tenant_policies(tenant_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS tenant_policies")
