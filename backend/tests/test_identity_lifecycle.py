from types import SimpleNamespace

import httpx
from fastapi import HTTPException
import pytest

from app import main
from app.db import get_admin_db
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


class ExecuteDatabase:
    def __init__(self, *rows):
        self.rows = iter(rows)
        self.added = []
        self.committed = False

    async def execute(self, _statement):
        return SimpleNamespace(first=lambda: next(self.rows))

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


@pytest.mark.asyncio
async def test_email_verification_http_loop_returns_debug_token_and_confirms_once(monkeypatch):
    user = User(id="user-4", email="verify@example.com", email_verified=False, is_active=True)
    tenant = SimpleNamespace(id="tenant-1", slug="acme", is_active=True)
    membership = SimpleNamespace(id="membership-4", tenant_id="tenant-1", is_active=True)
    request_db = ExecuteDatabase((user, membership, tenant))
    confirm_db = ExecuteDatabase((user, tenant, membership))
    settings = SimpleNamespace(
        app_env="test",
        redis_url="redis://unavailable",
        frontend_base_url="http://localhost:13000",
        password_reset_ttl_minutes=30,
        smtp_host="",
        smtp_from="",
    )

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    token = "email-token-1-abcdefghijklmnopqrstuvwxyz"
    monkeypatch.setattr(main, "create_email_verification", lambda *_args: _async_value(token))
    monkeypatch.setattr(main, "consume_email_verification", lambda _token: _async_value({"user_id": "user-4", "tenant_id": "tenant-1"}))

    async def override_request_db():
        yield request_db

    async def override_confirm_db():
        yield confirm_db

    transport = httpx.ASGITransport(app=main.app)
    main.app.dependency_overrides[get_admin_db] = override_request_db
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            requested = await client.post("/api/auth/email-verification/request", json={"email": user.email, "tenant_slug": "acme"})
            assert requested.status_code == 200
            assert requested.json() == {"accepted": True, "expires_in": 1800, "debug_token": token}
    finally:
        main.app.dependency_overrides.pop(get_admin_db, None)

    main.app.dependency_overrides[get_admin_db] = override_confirm_db
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            confirmed = await client.post("/api/auth/email-verification/confirm", json={"token": token})
            assert confirmed.status_code == 200
            assert confirmed.json() == {"verified": True, "email": user.email}
            assert user.email_verified is True
            assert confirm_db.committed is True
    finally:
        main.app.dependency_overrides.pop(get_admin_db, None)


@pytest.mark.asyncio
async def test_email_verification_request_does_not_disclose_unknown_accounts(monkeypatch):
    settings = SimpleNamespace(
        app_env="production",
        redis_url="redis://unavailable",
        frontend_base_url="https://example.com",
        password_reset_ttl_minutes=30,
        smtp_host="",
        smtp_from="",
    )
    database = ExecuteDatabase(None)
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    async def override_db():
        yield database

    transport = httpx.ASGITransport(app=main.app)
    main.app.dependency_overrides[get_admin_db] = override_db
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/auth/email-verification/request", json={"email": "unknown@example.com"})
        assert response.status_code == 200
        assert response.json() == {"accepted": True, "expires_in": 1800}
        assert database.committed is False
    finally:
        main.app.dependency_overrides.pop(get_admin_db, None)


async def _async_value(value):
    return value

