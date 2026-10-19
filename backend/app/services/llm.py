import asyncio
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import ModelHealthCheck, ModelProvider
from ..security import decrypt_secret
from .observability import llm_calls


RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _breaker_key(tenant_id: str, provider_id: str) -> str:
    return f"ai_platform:model_breaker:{tenant_id}:{provider_id}"


async def _breaker_count(tenant_id: str, provider_id: str) -> int:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1)
    try:
        return int(await redis.get(_breaker_key(tenant_id, provider_id)) or 0)
    except Exception:
        return 0
    finally:
        await redis.aclose()


async def _breaker_record(tenant_id: str, provider_id: str, success: bool) -> None:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1)
    try:
        key = _breaker_key(tenant_id, provider_id)
        if success:
            await redis.delete(key)
        else:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
    except Exception:
        pass
    finally:
        await redis.aclose()


def rank_providers(providers: list[ModelProvider], health: dict[str, ModelHealthCheck]) -> list[ModelProvider]:
    def rank(provider: ModelProvider):
        check = health.get(provider.id)
        priority = (provider.config_json or {}).get("priority", 100)
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 100
        return (check is not None and not check.ok, priority, check.latency_ms if check else 10**9, provider.id)
    return sorted(providers, key=rank)


async def call_routed_chat(
    db: AsyncSession,
    messages: list[dict[str, str]],
    *,
    tenant_id: str,
    preferred_provider_id: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    providers = (await db.execute(select(ModelProvider).where(ModelProvider.tenant_id == tenant_id, ModelProvider.enabled.is_(True)))).scalars().all()
    if preferred_provider_id:
        preferred = next((item for item in providers if item.id == preferred_provider_id), None)
        if not preferred:
            raise RuntimeError("指定的模型提供商不可用")
        fallback_ids = (preferred.config_json or {}).get("fallback_provider_ids") or []
        if not isinstance(fallback_ids, list):
            fallback_ids = []
        allowed = {preferred_provider_id, *fallback_ids}
        providers = [item for item in providers if item.id in allowed]
    if not providers:
        raise RuntimeError("没有可用的模型提供商")
    latest = {}
    for provider in providers:
        latest[provider.id] = await db.scalar(select(ModelHealthCheck).where(ModelHealthCheck.provider_id == provider.id, ModelHealthCheck.tenant_id == tenant_id).order_by(desc(ModelHealthCheck.created_at)))
    ordered = rank_providers(providers, latest)
    if preferred_provider_id:
        ordered.sort(key=lambda item: item.id != preferred_provider_id)
    last_error: Exception | None = None
    for provider in ordered:
        if await _breaker_count(tenant_id, provider.id) >= 3:
            continue
        try:
            result = await call_chat(db, provider, messages, tenant_id=tenant_id, model=model if provider.id == preferred_provider_id else None, temperature=temperature, max_tokens=max_tokens)
            await _breaker_record(tenant_id, provider.id, True)
            return {**result, "provider_id": provider.id, "model": model if provider.id == preferred_provider_id and model else provider.default_model}
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in RETRYABLE_STATUS:
                raise
            await _breaker_record(tenant_id, provider.id, False)
            last_error = exc
    if last_error is None:
        raise RuntimeError("模型提供商正在熔断，请稍后重试")
    raise last_error


async def call_chat(
    db: AsyncSession,
    provider: ModelProvider,
    messages: list[dict[str, str]],
    *,
    tenant_id: str,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    if not provider.enabled:
        raise RuntimeError("模型提供商已禁用")
    base_url = provider.base_url.rstrip("/")
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    api_key = decrypt_secret(provider.api_key_encrypted)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {
        "model": model or provider.default_model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    try:
        async with httpx.AsyncClient(timeout=get_settings().model_timeout_seconds) as client:
            for attempt in range(3):
                try:
                    response = await client.post(endpoint, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    break
                except httpx.HTTPStatusError as exc:
                    if attempt == 2 or exc.response.status_code not in RETRYABLE_STATUS:
                        raise
                except httpx.RequestError:
                    if attempt == 2:
                        raise
                await asyncio.sleep(min(2 ** attempt, 4))
        llm_calls.labels(tenant_id, provider.name, "success").inc()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return {"text": message.get("content", ""), "raw": data, "usage": data.get("usage", {})}
    except Exception:
        llm_calls.labels(tenant_id, provider.name, "error").inc()
        raise
