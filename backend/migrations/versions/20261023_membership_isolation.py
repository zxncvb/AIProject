"""Make identity deprovisioning tenant-scoped."""

from alembic import op


revision = "20261023_membership_isolation"
down_revision = "20261023_cron_schedules"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE memberships ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true")
    op.execute("CREATE INDEX IF NOT EXISTS ix_memberships_is_active ON memberships(is_active)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_memberships_is_active")
    op.execute("ALTER TABLE memberships DROP COLUMN IF EXISTS is_active")
