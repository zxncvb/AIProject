"""Add a database-backed hash chain for tenant audit events."""

from alembic import op


revision = "20261023_audit_hash_chain"
down_revision = "20261023_scim_groups"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS prev_hash varchar(64) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS event_hash varchar(64) NOT NULL DEFAULT ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_event_hash ON audit_events(event_hash)")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""
    CREATE OR REPLACE FUNCTION set_audit_event_hash() RETURNS trigger AS $$
    DECLARE previous_hash text;
    BEGIN
      PERFORM pg_advisory_xact_lock(hashtextextended(NEW.tenant_id, 0));
      SELECT event_hash INTO previous_hash
      FROM audit_events
      WHERE tenant_id = NEW.tenant_id AND event_hash <> ''
      ORDER BY created_at DESC, id DESC
      LIMIT 1;
      NEW.prev_hash := COALESCE(previous_hash, '');
      NEW.event_hash := encode(digest(
        COALESCE(NEW.prev_hash, '') || '|' || NEW.id || '|' || NEW.tenant_id || '|' ||
        COALESCE(NEW.actor_id, '') || '|' || COALESCE(NEW.action, '') || '|' ||
        COALESCE(NEW.resource_type, '') || '|' || COALESCE(NEW.resource_id, '') || '|' ||
        COALESCE(NEW.created_at::text, '') || '|' || COALESCE(NEW.detail_json::text, '{}'),
        'sha256'
      ), 'hex');
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS audit_event_hash_trigger ON audit_events")
    op.execute("""
    CREATE TRIGGER audit_event_hash_trigger
    BEFORE INSERT ON audit_events
    FOR EACH ROW EXECUTE FUNCTION set_audit_event_hash()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_event_hash_trigger ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS set_audit_event_hash()")
    op.execute("DROP INDEX IF EXISTS ix_audit_events_event_hash")
    op.execute("ALTER TABLE audit_events DROP COLUMN IF EXISTS event_hash")
    op.execute("ALTER TABLE audit_events DROP COLUMN IF EXISTS prev_hash")
