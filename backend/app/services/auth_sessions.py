"""Short-lived authentication state kept outside the relational schema."""

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone

from redis.asyncio import Redis

from ..config import get_settings


_fallback_failures: dict[str, tuple[int, float]] = {}
_fallback_locks: dict[str, float] = {}
_fallback_revoked: dict[str, float] = {}
_fallback_user_revoked: dict[str, float] = {}
_fallback_password_resets: dict[str, tuple[str, float]] = {}
_fallback_email_verifications: dict[str, tuple[str, float]] = {}


def _identity(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def _password_reset_key(token: str) -> str:
    return f"auth:password-reset:{hashlib.sha256(token.encode()).hexdigest()}"


def _email_verification_key(token: str) -> str:
    return f"auth:email-verification:{hashlib.sha256(token.encode()).hexdigest()}"


async def create_password_reset(user_id: str, tenant_id: str, ttl_seconds: int) -> str:
    raw_token = secrets.token_urlsafe(48)
    payload = json.dumps({"user_id": user_id, "tenant_id": tenant_id}, separators=(",", ":"))
    key = _password_reset_key(raw_token)
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        await redis.setex(key, max(60, ttl_seconds), payload)
    except Exception:
        _fallback_password_resets[key] = (payload, time.time() + max(60, ttl_seconds))
    finally:
        await redis.aclose()
    return raw_token


async def consume_password_reset(raw_token: str) -> dict | None:
    key = _password_reset_key(raw_token)
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    stored = None
    try:
        try:
            payload = await redis.getdel(key)
        except Exception:
            payload = await redis.get(key)
            if payload:
                await redis.delete(key)
        if not payload:
            stored = _fallback_password_resets.pop(key, None)
            if stored and stored[1] > time.time():
                payload = stored[0]
    except Exception:
        stored = _fallback_password_resets.pop(key, None)
        if not stored or stored[1] <= time.time():
            return None
        payload = stored[0]
    finally:
        await redis.aclose()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


async def create_email_verification(user_id: str, tenant_id: str, ttl_seconds: int) -> str:
    raw_token = secrets.token_urlsafe(48)
    payload = json.dumps({"user_id": user_id, "tenant_id": tenant_id}, separators=(",", ":"))
    key = _email_verification_key(raw_token)
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        await redis.setex(key, max(60, ttl_seconds), payload)
    except Exception:
        _fallback_email_verifications[key] = (payload, time.time() + max(60, ttl_seconds))
    finally:
        await redis.aclose()
    return raw_token


async def consume_email_verification(raw_token: str) -> dict | None:
    key = _email_verification_key(raw_token)
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    stored = None
    try:
        try:
            payload = await redis.getdel(key)
        except Exception:
            payload = await redis.get(key)
            if payload:
                await redis.delete(key)
        if not payload:
            stored = _fallback_email_verifications.pop(key, None)
            if stored and stored[1] > time.time():
                payload = stored[0]
    except Exception:
        stored = _fallback_email_verifications.pop(key, None)
        if not stored or stored[1] <= time.time():
            return None
        payload = stored[0]
    finally:
        await redis.aclose()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


async def _redis_get(key: str):
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        return await redis.get(key)
    except Exception:
        return None
    finally:
        await redis.aclose()


async def is_login_locked(email: str) -> bool:
    key = _identity(email)
    remote = await _redis_get(f"auth:login:lock:{key}")
    if remote is not None:
        return True
    return _fallback_locks.get(key, 0) > time.time()


async def record_login_failure(email: str) -> bool:
    key = _identity(email)
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        count = int(await redis.incr(f"auth:login:failure:{key}"))
        await redis.expire(f"auth:login:failure:{key}", settings.login_lock_minutes * 60)
        if count >= settings.login_failure_limit:
            await redis.setex(f"auth:login:lock:{key}", settings.login_lock_minutes * 60, "1")
            return True
        return False
    except Exception:
        current, expires = _fallback_failures.get(key, (0, 0))
        if expires <= time.time():
            current = 0
        current += 1
        _fallback_failures[key] = (current, time.time() + settings.login_lock_minutes * 60)
        if current >= settings.login_failure_limit:
            _fallback_locks[key] = time.time() + settings.login_lock_minutes * 60
            return True
        return False
    finally:
        await redis.aclose()


async def clear_login_failures(email: str) -> None:
    key = _identity(email)
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        await redis.delete(f"auth:login:failure:{key}", f"auth:login:lock:{key}")
    except Exception:
        pass
    finally:
        await redis.aclose()
    _fallback_failures.pop(key, None)
    _fallback_locks.pop(key, None)


async def revoke_token(jti: str, expires_at: int | float | None) -> None:
    if not jti:
        return
    ttl = max(1, int((float(expires_at or time.time()) - time.time())))
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        await redis.setex(f"auth:revoked:jti:{jti}", ttl, "1")
    except Exception:
        _fallback_revoked[jti] = time.time() + ttl
    finally:
        await redis.aclose()


async def revoke_user_sessions(user_id: str) -> None:
    timestamp = time.time()
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        await redis.set(f"auth:revoked:user:{user_id}", str(timestamp), ex=365 * 24 * 3600)
    except Exception:
        _fallback_user_revoked[user_id] = timestamp
    finally:
        await redis.aclose()


async def is_token_revoked(claims: dict) -> bool:
    jti = str(claims.get("jti") or "")
    user_id = str(claims.get("sub") or "")
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        if jti and await redis.exists(f"auth:revoked:jti:{jti}"):
            return True
        revoked_at = await redis.get(f"auth:revoked:user:{user_id}")
    except Exception:
        if jti and _fallback_revoked.get(jti, 0) > time.time():
            return True
        revoked_at = _fallback_user_revoked.get(user_id)
    finally:
        await redis.aclose()
    if not revoked_at:
        return False
    issued_at = claims.get("iat")
    if isinstance(issued_at, datetime):
        issued_at = issued_at.timestamp()
    return float(issued_at or 0) <= float(revoked_at)
