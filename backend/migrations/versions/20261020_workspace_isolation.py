"""Bind projects to workspaces for member-level isolation."""
from alembic import op


revision = "20261020_workspace_isolation"
down_revision = "20261020_workflow_reliability"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS workspace_id varchar(36) NULL REFERENCES workspaces(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_workspace_id ON projects(workspace_id)")
    op.execute(
        """
        UPDATE projects AS project
        SET workspace_id = (
          SELECT workspace.id
          FROM workspaces AS workspace
          WHERE workspace.tenant_id = project.tenant_id
          ORDER BY workspace.created_at, workspace.id
          LIMIT 1
        )
        WHERE project.workspace_id IS NULL
        """
    )
    for table in ("agent_configs", "prompt_templates", "database_connections"):
        op.execute(
            f"""
            UPDATE {table} AS resource
            SET workspace_id = (
              SELECT workspace.id
              FROM workspaces AS workspace
              WHERE workspace.tenant_id = resource.tenant_id
              ORDER BY workspace.created_at, workspace.id
              LIMIT 1
            )
            WHERE resource.workspace_id IS NULL
            """
        )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_projects_workspace_id")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS workspace_id")
