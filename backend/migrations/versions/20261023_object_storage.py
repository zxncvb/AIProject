"""Add object-storage metadata for uploaded documents."""

from alembic import op


revision = "20261023_object_storage"
down_revision = "20261023_membership_isolation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_key varchar(500) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_backend varchar(30) NOT NULL DEFAULT 'local'")


def downgrade():
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS storage_backend")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS storage_key")
