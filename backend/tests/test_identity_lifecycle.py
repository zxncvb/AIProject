from types import SimpleNamespace

import pytest

from app import main
from app.models import Membership, User
from app.schemas import MemberRoleUpdate


class MemberDatabase:
    def __init__(self, membership, user):
        self.membership = membership
        self.user = user
        self.added = []
        self.committed = False

    async def scalar(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is Membership:
            return self.membership
        if entity is User:
            return self.user
        return None

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True

    async def delete(self, _value):
        return None


@pytest.mark.asyncio
async def test_member_permission_change_revokes_existing_sessions(monkeypatch):
    membership = Membership(user_id="user-2", tenant_id="tenant-1", role="viewer", is_active=True)
    membership.id = "membership-1"
    user = User(id="user-2", email="user@example.com", display_name="User", password_hash="hash")
    db = MemberDatabase(membership, user)
    revoked = []
    async def revoke(user_id):
        revoked.append(user_id)

    monkeypatch.setattr(main, "revoke_user_sessions", revoke)
    ctx = SimpleNamespace(user_id="admin-1", tenant_id="tenant-1")

    result = await main.update_member("user-2", MemberRoleUpdate(role="operator"), ctx, db)

    assert result["role"] == "operator"
    assert result["sessions_revoked"] is True
    assert revoked == ["user-2"]
    assert db.committed is True


@pytest.mark.asyncio
async def test_member_removal_revokes_existing_sessions(monkeypatch):
    membership = Membership(user_id="user-2", tenant_id="tenant-1", role="viewer", is_active=True)
    membership.id = "membership-1"
    db = MemberDatabase(membership, User(id="user-2", email="user@example.com", password_hash="hash"))
    revoked = []
    async def revoke(user_id):
        revoked.append(user_id)

    monkeypatch.setattr(main, "revoke_user_sessions", revoke)
    ctx = SimpleNamespace(user_id="admin-1", tenant_id="tenant-1")

    result = await main.remove_member("user-2", ctx, db)

    assert result["removed"] is True
    assert revoked == ["user-2"]
    assert db.committed is True

