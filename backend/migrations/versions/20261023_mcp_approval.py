"""Require approval before an MCP service can be tested or invoked."""

from alembic import op


revision = "20261023_mcp_approval"
down_revision = ("20261023_audit_append_only", "20261023_public_callback_outbox")
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS approval_status varchar(30) NOT NULL DEFAULT 'pending'")
    op.execute("ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS approved_by varchar(36) REFERENCES users(id)")
    op.execute("ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS approved_at timestamptz")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mcp_servers_approval_status ON mcp_servers(approval_status)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_mcp_servers_approval_status")
    op.execute("ALTER TABLE mcp_servers DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE mcp_servers DROP COLUMN IF EXISTS approved_by")
    op.execute("ALTER TABLE mcp_servers DROP COLUMN IF EXISTS approval_status")
