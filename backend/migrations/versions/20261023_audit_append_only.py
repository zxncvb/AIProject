"""Make the tenant audit log append-only after hash-chain installation."""

from alembic import op


revision = "20261023_audit_append_only"
down_revision = "20261023_public_callback_outbox"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE OR REPLACE FUNCTION reject_audit_event_mutation() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'audit_events is append-only';
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS audit_event_append_only_trigger ON audit_events")
    op.execute("""
    CREATE TRIGGER audit_event_append_only_trigger
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_event_append_only_trigger ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_event_mutation()")
