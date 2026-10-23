-- PostgreSQL row-level security for the runtime database role.
-- Apply after bootstrap with a dedicated non-owner role, for example:
--   CREATE ROLE platform_runtime LOGIN PASSWORD '...';
--   GRANT ... TO platform_runtime;
--   \i deploy/postgres/rls.sql
-- The API sets SET LOCAL app.tenant_id for every authenticated request.

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'memberships', 'projects', 'model_providers', 'agents', 'workflows',
    'workflow_versions', 'workflow_runs', 'knowledge_bases', 'documents',
    'document_chunks', 'skills', 'plugins', 'audit_events', 'workflow_releases',
    'workflow_schedules', 'applications', 'application_versions', 'compute_quotas', 'compute_usage',
    'roles', 'knowledge_base_access', 'mcp_servers', 'model_health_checks', 'tenant_policies', 'scim_tokens',
    'gpu_leases', 'sandbox_runs', 'evaluation_jobs', 'model_conversations',
    'knowledge_assets', 'agent_events', 'api_keys', 'organizations', 'workspaces',
    'workspace_members', 'agent_configs', 'agent_versions', 'prompt_templates',
    'database_connections', 'marketplace_items', 'favorites', 'publish_channels',
    'publish_bindings', 'approval_requests', 'intervention_rules',
    'application_builds', 'application_deployments', 'publish_deliveries',
    'approval_policies', 'approval_votes', 'scim_groups', 'scim_group_members',
    'vendor_billing_records', 'agent_conversations', 'agent_memories', 'application_access_logs'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', table_name);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))',
      table_name
    );
  END LOOP;
END $$;

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_self ON tenants;
CREATE POLICY tenant_self ON tenants
  USING (id = current_setting('app.tenant_id', true));
