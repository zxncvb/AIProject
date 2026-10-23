"""Add tenant-scoped SCIM Groups and membership records."""

from alembic import op


revision = "20261023_scim_groups"
down_revision = "20261023_object_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS scim_groups (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      display_name varchar(160) NOT NULL,
      external_id varchar(160) NOT NULL DEFAULT '',
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_scim_group_tenant_name UNIQUE(tenant_id, display_name)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_scim_groups_tenant_id ON scim_groups(tenant_id)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS scim_group_members (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      group_id varchar(36) NOT NULL REFERENCES scim_groups(id) ON DELETE CASCADE,
      user_id varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_scim_group_member UNIQUE(group_id, user_id)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_scim_group_members_tenant_id ON scim_group_members(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scim_group_members_group_id ON scim_group_members(group_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scim_group_members_user_id ON scim_group_members(user_id)")
    for table in ("scim_groups", "scim_group_members"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))''')


def downgrade():
    op.execute("DROP TABLE IF EXISTS scim_group_members")
    op.execute("DROP TABLE IF EXISTS scim_groups")
