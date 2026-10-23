"""Add cron, timezone, and misfire settings to workflow schedules."""

from alembic import op


revision = "20261023_cron_schedules"
down_revision = "20261021_admin_name_localization"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE workflow_schedules ALTER COLUMN interval_seconds DROP NOT NULL")
    op.execute("ALTER TABLE workflow_schedules ADD COLUMN IF NOT EXISTS cron_expression varchar(120) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE workflow_schedules ADD COLUMN IF NOT EXISTS timezone varchar(80) NOT NULL DEFAULT 'UTC'")
    op.execute("ALTER TABLE workflow_schedules ADD COLUMN IF NOT EXISTS misfire_policy varchar(20) NOT NULL DEFAULT 'skip'")


def downgrade():
    op.execute("ALTER TABLE workflow_schedules DROP COLUMN IF EXISTS misfire_policy")
    op.execute("ALTER TABLE workflow_schedules DROP COLUMN IF EXISTS timezone")
    op.execute("ALTER TABLE workflow_schedules DROP COLUMN IF EXISTS cron_expression")
    op.execute("DELETE FROM workflow_schedules WHERE interval_seconds IS NULL")
    op.execute("ALTER TABLE workflow_schedules ALTER COLUMN interval_seconds SET NOT NULL")
