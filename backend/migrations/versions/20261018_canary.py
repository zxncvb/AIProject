"""Add workflow release traffic percentage."""
from alembic import op

revision = "20261018_canary"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE workflow_releases ADD COLUMN IF NOT EXISTS traffic_percent integer NOT NULL DEFAULT 100")
    op.execute("ALTER TABLE workflow_releases DROP CONSTRAINT IF EXISTS workflow_releases_traffic_percent_check")
    op.execute("ALTER TABLE workflow_releases ADD CONSTRAINT workflow_releases_traffic_percent_check CHECK (traffic_percent BETWEEN 1 AND 100)")


def downgrade():
    op.execute("ALTER TABLE workflow_releases DROP CONSTRAINT IF EXISTS workflow_releases_traffic_percent_check")
    op.execute("ALTER TABLE workflow_releases DROP COLUMN IF EXISTS traffic_percent")
