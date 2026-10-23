"""Add tenant-scoped vendor billing imports for FinOps reconciliation."""

from alembic import op


revision = "20261023_vendor_billing"
down_revision = "20261023_audit_hash_chain"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS vendor_billing_records (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      provider_name varchar(120) NOT NULL,
      external_id varchar(180) NOT NULL,
      billing_period varchar(40) NOT NULL,
      currency varchar(12) NOT NULL DEFAULT 'CNY',
      billed_amount double precision NOT NULL DEFAULT 0,
      billed_tokens integer NOT NULL DEFAULT 0,
      billed_gpu_seconds integer NOT NULL DEFAULT 0,
      source_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      imported_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_vendor_billing_external UNIQUE(tenant_id, provider_name, external_id)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vendor_billing_tenant_id ON vendor_billing_records(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vendor_billing_period ON vendor_billing_records(billing_period)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vendor_billing_provider ON vendor_billing_records(provider_name)")
    op.execute("ALTER TABLE vendor_billing_records ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON vendor_billing_records")
    op.execute("CREATE POLICY tenant_isolation ON vendor_billing_records USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade():
    op.execute("DROP TABLE IF EXISTS vendor_billing_records")
