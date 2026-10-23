from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

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


class BootstrapLockDatabase:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))


class ConflictingTenantDatabase(ProvisioningDatabase):
    def __init__(self):
        super().__init__()
        self.rolled_back = False

    async def flush(self):
        raise IntegrityError("insert tenant", {}, RuntimeError("duplicate slug"))

    async def rollback(self):
        self.rolled_back = True


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


@pytest.mark.asyncio
async def test_postgres_bootstrap_uses_transaction_advisory_lock(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
        database_admin_url="postgresql+asyncpg://platform:secret@db/platform",
        database_url="",
    ))
    db = BootstrapLockDatabase()

    await main.acquire_bootstrap_lock(db)

    assert len(db.calls) == 1
    assert "pg_advisory_xact_lock" in db.calls[0][0]
    assert db.calls[0][1]["lock_key"].startswith("enterprise-ai-platform.bootstrap")


@pytest.mark.asyncio
async def test_concurrent_tenant_slug_conflict_returns_conflict(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(database_url="sqlite+aiosqlite:///test.db"))
    db = ConflictingTenantDatabase()

    with pytest.raises(HTTPException) as exc:
        await main.create_tenant(TenantCreate(name="客户租户", slug="customer-a"), SimpleNamespace(user_id="owner-1"), db)

    assert exc.value.status_code == 409
    assert db.rolled_back is True

