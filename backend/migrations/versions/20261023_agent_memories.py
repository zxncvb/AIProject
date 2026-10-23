"""Add tenant and user scoped long-term Agent memories."""

from alembic import op
import sqlalchemy as sa


revision = "20261023_agent_memories"
down_revision = "20261023_agent_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("memory_key", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_memories_tenant_id", "agent_memories", ["tenant_id"])
    op.create_index("ix_agent_memories_agent_id", "agent_memories", ["agent_id"])
    op.create_index("ix_agent_memories_user_id", "agent_memories", ["user_id"])
    op.create_index("ix_agent_memories_expires_at", "agent_memories", ["expires_at"])
    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_agent_memories ON agent_memories")
        op.execute("CREATE POLICY tenant_isolation_agent_memories ON agent_memories USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.drop_index("ix_agent_memories_expires_at", table_name="agent_memories")
    op.drop_index("ix_agent_memories_user_id", table_name="agent_memories")
    op.drop_index("ix_agent_memories_agent_id", table_name="agent_memories")
    op.drop_index("ix_agent_memories_tenant_id", table_name="agent_memories")
    op.drop_table("agent_memories")
