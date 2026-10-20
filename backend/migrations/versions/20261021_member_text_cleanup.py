"""Repair legacy member labels that were submitted with a non-UTF-8 client."""
from alembic import op


revision = "20261021_member_text_cleanup"
down_revision = "20261021_enterprise_completion"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE users
        SET display_name = 'SCIM 验收用户'
        WHERE display_name = 'SCIM ???'
          AND email LIKE 'scim-%@acme.local'
    """)


def downgrade():
    pass
