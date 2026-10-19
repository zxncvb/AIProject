"""Enable tenant RLS and grant the dedicated runtime role when present."""
from alembic import op


revision = "20261020_rls_enforcement"
down_revision = "20261020_workspace_isolation"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "memberships", "projects", "model_providers", "agents", "workflows",
    "workflow_versions", "workflow_runs", "knowledge_bases", "documents",
    "document_chunks", "skills", "plugins", "audit_events", "workflow_releases",
    "workflow_schedules", "applications", "application_versions", "compute_quotas",
    "compute_usage", "roles", "knowledge_base_access", "mcp_servers",
    "model_health_checks", "tenant_policies", "scim_tokens", "gpu_leases",
    "sandbox_runs", "evaluation_jobs", "model_conversations", "knowledge_assets",
    "agent_events", "api_keys", "organizations", "workspaces", "workspace_members",
    "agent_configs", "agent_versions", "prompt_templates", "database_connections",
    "marketplace_items", "favorites", "publish_channels", "publish_bindings",
    "approval_requests", "intervention_rules",
)


def upgrade():
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
                USING (tenant_id = current_setting('app.tenant_id', true))
                WITH CHECK (tenant_id = current_setting('app.tenant_id', true))'''
        )
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_self ON tenants")
    op.execute(
        "CREATE POLICY tenant_self ON tenants "
        "USING (id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (id = current_setting('app.tenant_id', true))"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_runtime') THEN
            GRANT USAGE ON SCHEMA public TO platform_runtime;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO platform_runtime;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO platform_runtime;
          END IF;
        END $$
        """
    )


def downgrade():
    op.execute("DROP POLICY IF EXISTS tenant_self ON tenants")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")
    for table in TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
