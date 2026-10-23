"""Persist public callback deliveries for durable retries."""

from alembic import op
import sqlalchemy as sa


revision = "20261023_public_callback_outbox"
# The two 2026-10-23 feature branches predated this migration. Keep the
# deployment graph explicit so `alembic upgrade head` has one deterministic
# head instead of failing on multiple heads.
down_revision = ("20261023_vendor_billing", "20261023_application_operations")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_callback_deliveries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("callback_url", sa.String(length=2000), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("response_status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "kind", "run_id", name="uq_public_callback_delivery_run"),
    )
    for name, column in (
        ("tenant_id", "tenant_id"),
        ("kind", "kind"),
        ("run_id", "run_id"),
        ("status", "status"),
        ("next_attempt_at", "next_attempt_at"),
        ("created_at", "created_at"),
    ):
        op.create_index(f"ix_public_callback_deliveries_{name}", "public_callback_deliveries", [column])
    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TABLE public_callback_deliveries ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_public_callback_deliveries ON public_callback_deliveries")
        op.execute("CREATE POLICY tenant_isolation_public_callback_deliveries ON public_callback_deliveries USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    for name in ("created_at", "next_attempt_at", "status", "run_id", "kind", "tenant_id"):
        op.drop_index(f"ix_public_callback_deliveries_{name}", table_name="public_callback_deliveries")
    op.drop_table("public_callback_deliveries")
