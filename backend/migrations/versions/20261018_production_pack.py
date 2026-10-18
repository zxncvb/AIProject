"""Add production management APIs and runtime registry tables."""
from alembic import op

revision = "20261018_production_pack"
down_revision = "20261018_platform_plus"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS roles (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      name varchar(120) NOT NULL,
      slug varchar(80) NOT NULL,
      description text NOT NULL DEFAULT '',
      permissions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      is_system boolean NOT NULL DEFAULT false,
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_role_tenant_slug UNIQUE (tenant_id, slug)
    )
    """)
    op.execute("ALTER TABLE memberships ADD COLUMN IF NOT EXISTS custom_role_id varchar(36) NULL REFERENCES roles(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_memberships_custom_role_id ON memberships(custom_role_id)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_base_access (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      knowledge_base_id varchar(36) NOT NULL REFERENCES knowledge_bases(id),
      user_id varchar(36) NOT NULL REFERENCES users(id),
      access_level varchar(30) NOT NULL DEFAULT 'reader',
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_kb_access_user UNIQUE (knowledge_base_id, user_id)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_access_kb_id ON knowledge_base_access(knowledge_base_id)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS mcp_servers (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      name varchar(160) NOT NULL,
      endpoint varchar(800) NOT NULL,
      transport varchar(30) NOT NULL DEFAULT 'streamable_http',
      manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      secret_encrypted text NOT NULL DEFAULT '',
      enabled boolean NOT NULL DEFAULT true,
      created_by varchar(36) NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_mcp_server_tenant_name UNIQUE (tenant_id, name)
    )
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS model_health_checks (
      id varchar(36) PRIMARY KEY,
      tenant_id varchar(36) NOT NULL REFERENCES tenants(id),
      provider_id varchar(36) NOT NULL REFERENCES model_providers(id),
      ok boolean NOT NULL DEFAULT false,
      latency_ms integer NOT NULL DEFAULT 0,
      status_code integer NOT NULL DEFAULT 0,
      detail text NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_model_health_provider_id ON model_health_checks(provider_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS model_health_checks")
    op.execute("DROP TABLE IF EXISTS mcp_servers")
    op.execute("DROP TABLE IF EXISTS knowledge_base_access")
    op.execute("ALTER TABLE memberships DROP COLUMN IF EXISTS custom_role_id")
    op.execute("DROP TABLE IF EXISTS roles")
