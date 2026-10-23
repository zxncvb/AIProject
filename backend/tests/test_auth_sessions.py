from types import SimpleNamespace
import time

import pytest

from app.services import auth_sessions


class BrokenRedis:
    async def get(self, *_args, **_kwargs):
        raise OSError("redis unavailable")

    async def getdel(self, *_args, **_kwargs):
        raise OSError("redis unavailable")

    async def setex(self, *_args, **_kwargs):
        raise OSError("redis unavailable")

    async def set(self, *_args, **_kwargs):
        raise OSError("redis unavailable")

    async def incr(self, *_args, **_kwargs):
        raise OSError("redis unavailable")

    async def expire(self, *_args, **_kwargs):
        raise OSError("redis unavailable")

    async def delete(self, *_args, **_kwargs):
        raise OSError("redis unavailable")

    async def exists(self, *_args, **_kwargs):
        raise OSError("redis unavailable")

    async def aclose(self):
        return None


@pytest.fixture(autouse=True)
def clear_fallback_state():
    for values in (
        auth_sessions._fallback_failures,
        auth_sessions._fallback_locks,
        auth_sessions._fallback_revoked,
        auth_sessions._fallback_user_revoked,
        auth_sessions._fallback_password_resets,
        auth_sessions._fallback_email_verifications,
    ):
        values.clear()
    yield
    for values in (
        auth_sessions._fallback_failures,
        auth_sessions._fallback_locks,
        auth_sessions._fallback_revoked,
        auth_sessions._fallback_user_revoked,
        auth_sessions._fallback_password_resets,
        auth_sessions._fallback_email_verifications,
    ):
        values.clear()


@pytest.fixture
def unavailable_redis(monkeypatch):
    monkeypatch.setattr(auth_sessions.Redis, "from_url", lambda *_args, **_kwargs: BrokenRedis())
    monkeypatch.setattr(
        auth_sessions,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://unavailable", login_failure_limit=2, login_lock_minutes=1),
    )


@pytest.mark.asyncio
async def test_login_failures_lock_and_clear_when_redis_is_unavailable(unavailable_redis):
    email = "admin@example.com"
    await auth_sessions.clear_login_failures(email)

    assert await auth_sessions.record_login_failure(email) is False
    assert await auth_sessions.record_login_failure(email) is True
    assert await auth_sessions.is_login_locked(email) is True

    await auth_sessions.clear_login_failures(email)
    assert await auth_sessions.is_login_locked(email) is False


@pytest.mark.asyncio
async def test_revocation_and_password_reset_fallbacks_are_one_time(unavailable_redis):
    token = await auth_sessions.create_password_reset("user-1", "tenant-1", 60)
    assert await auth_sessions.consume_password_reset(token) == {"user_id": "user-1", "tenant_id": "tenant-1"}
    assert await auth_sessions.consume_password_reset(token) is None

    await auth_sessions.revoke_token("jti-1", time.time() + 60)
    assert await auth_sessions.is_token_revoked({"jti": "jti-1", "sub": "user-1", "iat": time.time()}) is True

    await auth_sessions.revoke_user_sessions("user-1")
    assert await auth_sessions.is_token_revoked({"sub": "user-1", "iat": time.time() - 1}) is True
    assert await auth_sessions.is_token_revoked({"sub": "user-1", "iat": time.time() + 1}) is False


@pytest.mark.asyncio
async def test_email_verification_fallback_is_one_time(unavailable_redis):
    token = await auth_sessions.create_email_verification("user-1", "tenant-1", 60)
    assert await auth_sessions.consume_email_verification(token) == {"user_id": "user-1", "tenant_id": "tenant-1"}
    assert await auth_sessions.consume_email_verification(token) is None

