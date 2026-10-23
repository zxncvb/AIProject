"""Signed callbacks for public asynchronous application results."""

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings


logger = logging.getLogger("enterprise_ai_platform.public_callback")


def validate_public_callback_url(value: str | None) -> str:
    """Validate a callback endpoint against the configured egress allowlist."""
    callback_url = str(value or "").strip()
    if not callback_url:
        return ""
    parsed = urlparse(callback_url)
    settings = get_settings()
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("callback_url 必须是没有用户信息的 HTTP(S) URL")
    if settings.app_env.strip().lower() in {"production", "prod"} and parsed.scheme != "https":
        raise ValueError("生产环境 callback_url 必须使用 HTTPS")
    if parsed.hostname.lower() not in settings.allowed_hosts:
        raise ValueError("callback_url 主机不在允许的出站主机列表中")
    return callback_url


def _callback_signature(body: bytes) -> str:
    settings = get_settings()
    secret = (settings.publication_signing_secret or settings.app_secret_key).encode()
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def public_callback_payload(
    *,
    kind: str,
    run_id: str,
    tenant_id: str,
    status: str,
    output: Any = None,
    error: str = "",
    finished_at: Any = None,
) -> dict[str, Any]:
    return {
        "event": "public_application.run.completed",
        "kind": kind,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "status": status,
        "output": output if status == "succeeded" else None,
        "error": error if status in {"failed", "cancelled"} else None,
        "finished_at": finished_at,
    }


async def deliver_public_callback(callback_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST one signed callback with bounded retry for transient failures."""
    callback_url = validate_public_callback_url(callback_url)
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "enterprise-ai-platform-callback/1",
        "X-Enterprise-AI-Signature": _callback_signature(body),
        "X-Enterprise-AI-Event": str(payload.get("event") or "public_application.run.completed"),
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            timeout = httpx.Timeout(10.0, connect=3.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(callback_url, content=body, headers=headers)
                response.raise_for_status()
            return {"delivered": True, "attempts": attempt + 1, "status_code": response.status_code}
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code != 429 and exc.response.status_code < 500:
                return {"delivered": False, "attempts": attempt + 1, "status_code": exc.response.status_code, "error": str(exc)[:1000]}
            if attempt < 2:
                await asyncio.sleep(0.2 * (attempt + 1))
        except httpx.RequestError as exc:
            last_error = exc
            if attempt < 2:
                # Keep the worker bounded while allowing short endpoint hiccups
                # to recover; a later poll remains the source of truth.
                await asyncio.sleep(0.2 * (attempt + 1))
    logger.warning("public callback delivery failed after retries: %s", last_error)
    return {"delivered": False, "attempts": 3, "error": str(last_error or "callback failed")[:1000]}
