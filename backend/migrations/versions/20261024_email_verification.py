"""Add explicit email verification state for password accounts."""

from alembic import op


revision = "20261024_email_verification"
down_revision = "20261023_mcp_approval"
branch_labels = None
depends_on = None


def upgrade():
    # Existing accounts were created before this gate existed and are treated
    # as verified; newly-created password accounts use the model default false.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE users ALTER COLUMN email_verified SET DEFAULT false")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verified")
