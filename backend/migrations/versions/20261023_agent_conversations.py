"""Persist tenant-scoped Agent conversations for short-term memory."""

from alembic import op
import sqlalchemy as sa


revision = "20261023_agent_conversations"
down_revision = "20261023_vendor_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False, server_default="新会话"),
        sa.Column("messages_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_conversations_tenant_id", "agent_conversations", ["tenant_id"])
    op.create_index("ix_agent_conversations_agent_id", "agent_conversations", ["agent_id"])
    op.create_index("ix_agent_conversations_user_id", "agent_conversations", ["user_id"])
    op.create_index("ix_agent_conversations_updated_at", "agent_conversations", ["updated_at"])
    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_agent_conversations ON agent_conversations")
        op.execute("CREATE POLICY tenant_isolation_agent_conversations ON agent_conversations USING (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.drop_index("ix_agent_conversations_updated_at", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_user_id", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_agent_id", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_tenant_id", table_name="agent_conversations")
    op.drop_table("agent_conversations")
