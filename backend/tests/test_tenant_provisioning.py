from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import main
from app.models import (
    AuditEvent,
    Membership,
    Organization,
    Project,
    PublishChannel,
    Role,
    Tenant,
    TenantPolicy,
    Workspace,
    WorkspaceMember,
)
from app.schemas import TenantCreate


class ProvisioningDatabase:
    """Small async unit-test double for the admin-side provisioning path."""

    def __init__(self):
        self.added = []

    async def scalar(self, _statement):
        return None

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if hasattr(value, "id") and not value.id:
                value.id = str(uuid4())

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_tenant_creation_provisions_usable_defaults(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
        safety_mode="redact",
        safety_max_input_chars=12000,
        safety_block_prompt_injection=False,
        finops_currency="CNY",
        finops_token_price_per_1k=0.02,
        finops_gpu_price_per_second=0.0005,
        finops_cpu_price_per_second=0.00001,
    ))
    db = ProvisioningDatabase()
    ctx = SimpleNamespace(user_id="owner-1")

    result = await main.create_tenant(TenantCreate(name="客户租户", slug="customer-a"), ctx, db)

    assert result["role"] == "owner"
    assert result["defaults"]["workspace_id"]
    assert any(isinstance(row, Membership) and row.role == "owner" for row in db.added)
    assert any(isinstance(row, Project) and row.slug == "platform" for row in db.added)
    assert any(isinstance(row, Organization) and row.code == "default" for row in db.added)
    assert any(isinstance(row, Workspace) and row.slug == "default" for row in db.added)
    assert any(isinstance(row, WorkspaceMember) and row.role == "owner" for row in db.added)
    assert sum(isinstance(row, PublishChannel) for row in db.added) == 8
    assert {row.slug for row in db.added if isinstance(row, Role)} == {"owner", "admin", "operator", "developer", "viewer"}
    assert any(isinstance(row, TenantPolicy) for row in db.added)
    assert any(isinstance(row, AuditEvent) and row.action == "tenant.create" for row in db.added)

