"""Add cost centers for FinOps attribution and observability exports."""
from alembic import op

revision = "20261019_finops_observability"
down_revision = "20261018_priority_runtime"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS cost_center varchar(120) NOT NULL DEFAULT 'unassigned'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_runs_cost_center ON workflow_runs(cost_center)")
    op.execute("ALTER TABLE compute_usage ADD COLUMN IF NOT EXISTS cost_center varchar(120) NOT NULL DEFAULT 'unassigned'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_compute_usage_cost_center ON compute_usage(cost_center)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_compute_usage_cost_center")
    op.execute("ALTER TABLE compute_usage DROP COLUMN IF EXISTS cost_center")
    op.execute("DROP INDEX IF EXISTS ix_workflow_runs_cost_center")
    op.execute("ALTER TABLE workflow_runs DROP COLUMN IF EXISTS cost_center")
