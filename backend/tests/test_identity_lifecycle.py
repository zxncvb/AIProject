from types import SimpleNamespace

from fastapi import HTTPException
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


class LoginResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class LoginDatabase:
    def __init__(self, user, membership, tenant):
        self.user = user
        self.row = (membership, tenant)
        self.added = []
        self.committed = False

    async def scalar(self, _statement):
        return self.user

    async def execute(self, _statement):
        return LoginResult(self.row)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True


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


@pytest.mark.asyncio
async def test_password_login_requires_verified_email(monkeypatch):
    user = User(id="user-3", email="unverified@example.com", password_hash=main.hash_password("correct-password"), email_verified=False)
    membership = SimpleNamespace(role="viewer")
    tenant = SimpleNamespace(id="tenant-1", name="Acme", slug="acme")
    db = LoginDatabase(user, membership, tenant)

    async def unlocked(_email):
        return False

    monkeypatch.setattr(main, "is_login_locked", unlocked)
    monkeypatch.setattr(main, "clear_login_failures", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as error:
        await main.login(
            SimpleNamespace(email=user.email, password="correct-password", tenant_slug=None, mfa_code=None),
            SimpleNamespace(),
            None,
            db,
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "email_verification_required"
    assert db.committed is True
    assert any(getattr(item, "action", "") == "auth.login.blocked" for item in db.added)

