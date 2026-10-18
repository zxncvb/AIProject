"""Add MFA and SCIM provisioning support."""
from alembic import op

revision = "20261018_priority_identity"
down_revision = "20261018_enterprise_pack"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret_encrypted text NOT NULL DEFAULT ''")
    op.execute("""
    CREATE TABLE IF NOT EXISTS scim_tokens (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      name varchar(120) NOT NULL,
      token_hash varchar(64) NOT NULL,
      enabled boolean NOT NULL DEFAULT true,
      last_used_at timestamptz NULL,
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_scim_token_tenant_hash UNIQUE (tenant_id, token_hash)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_scim_tokens_token_hash ON scim_tokens(token_hash)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS scim_tokens")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_secret_encrypted")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_enabled")
