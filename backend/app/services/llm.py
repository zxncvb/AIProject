from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import ModelProvider
from ..security import decrypt_secret
from .observability import llm_calls


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
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        llm_calls.labels(tenant_id, provider.name, "success").inc()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return {"text": message.get("content", ""), "raw": data, "usage": data.get("usage", {})}
    except Exception:
        llm_calls.labels(tenant_id, provider.name, "error").inc()
        raise
