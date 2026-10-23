"""Add application domains, per-app quotas, and access logs."""

from alembic import op
import sqlalchemy as sa


revision = "20261023_application_operations"
down_revision = "20261023_agent_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("custom_domain", sa.String(length=253), nullable=False, server_default=""))
    op.add_column("applications", sa.Column("tls_secret_name", sa.String(length=253), nullable=False, server_default=""))
    op.add_column("applications", sa.Column("public_rate_limit_per_minute", sa.Integer(), nullable=False, server_default="120"))
    op.create_table(
        "application_access_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("application_id", sa.String(length=36), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_ip_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_application_access_logs_tenant_id", "application_access_logs", ["tenant_id"])
    op.create_index("ix_application_access_logs_application_id", "application_access_logs", ["application_id"])
    op.create_index("ix_application_access_logs_request_id", "application_access_logs", ["request_id"])
    op.create_index("ix_application_access_logs_created_at", "application_access_logs", ["created_at"])
    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TABLE application_access_logs ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_application_access_logs ON application_access_logs")
        op.execute("CREATE POLICY tenant_isolation_application_access_logs ON application_access_logs USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.drop_index("ix_application_access_logs_created_at", table_name="application_access_logs")
    op.drop_index("ix_application_access_logs_request_id", table_name="application_access_logs")
    op.drop_index("ix_application_access_logs_application_id", table_name="application_access_logs")
    op.drop_index("ix_application_access_logs_tenant_id", table_name="application_access_logs")
    op.drop_table("application_access_logs")
    op.drop_column("applications", "public_rate_limit_per_minute")
    op.drop_column("applications", "tls_secret_name")
    op.drop_column("applications", "custom_domain")
