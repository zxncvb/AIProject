"""Localize the legacy bootstrap administrator display name."""
from alembic import op


revision = "20261021_admin_name_localization"
down_revision = "20261021_member_text_cleanup"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE users SET display_name = '平台管理员' WHERE display_name = 'Platform Administrator'")


def downgrade():
    op.execute("UPDATE users SET display_name = 'Platform Administrator' WHERE display_name = '平台管理员'")
