"""Signed callbacks for public asynchronous application results."""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import or_, select

from ..config import get_settings
from ..db import AdminSessionLocal
from ..models import PublicCallbackDelivery, utcnow


logger = logging.getLogger("enterprise_ai_platform.public_callback")
MAX_DELIVERY_ATTEMPTS = 8
DELIVERY_BACKOFF_SECONDS = (1, 5, 30, 120, 600, 1800, 3600)


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


async def deliver_public_callback(callback_url: str, payload: dict[str, Any], *, delivery_id: str = "") -> dict[str, Any]:
    """POST one signed callback with bounded retry for transient failures."""
    callback_url = validate_public_callback_url(callback_url)
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "enterprise-ai-platform-callback/1",
        "X-Enterprise-AI-Signature": _callback_signature(body),
        "X-Enterprise-AI-Event": str(payload.get("event") or "public_application.run.completed"),
    }
    if delivery_id:
        headers["X-Enterprise-AI-Delivery-ID"] = delivery_id
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


async def _claim_delivery(delivery_id: str) -> PublicCallbackDelivery | None:
    """Claim one due delivery with a lease so multiple workers do not duplicate it."""
    now = utcnow()
    async with AdminSessionLocal() as db:
        statement = (
            select(PublicCallbackDelivery)
            .where(
                PublicCallbackDelivery.id == delivery_id,
                PublicCallbackDelivery.next_attempt_at <= now,
                or_(
                    PublicCallbackDelivery.status == "queued",
                    (PublicCallbackDelivery.status == "sending") & (PublicCallbackDelivery.lease_until < now),
                ),
            )
            .with_for_update(skip_locked=True)
        )
        row = await db.scalar(statement)
        if not row:
            return None
        row.status = "sending"
        row.attempts = int(row.attempts or 0) + 1
        row.lease_until = now + timedelta(minutes=5)
        await db.commit()
        return row


async def deliver_public_callback_delivery(delivery_id: str) -> dict[str, Any]:
    """Deliver a persisted callback and retain failures for later worker retries."""
    row = await _claim_delivery(delivery_id)
    if not row:
        return {"delivered": False, "claimed": False}
    try:
        result = await deliver_public_callback(row.callback_url, row.payload_json, delivery_id=row.id)
    except Exception as exc:  # validation/config errors must not kill the worker
        result = {"delivered": False, "error": str(exc)[:1000]}
    now = utcnow()
    async with AdminSessionLocal() as db:
        current = await db.scalar(select(PublicCallbackDelivery).where(PublicCallbackDelivery.id == row.id))
        if not current:
            return result
        current.lease_until = None
        current.response_status = int(result.get("status_code") or 0)
        if result.get("delivered"):
            current.status = "succeeded"
            current.delivered_at = now
            current.last_error = ""
        elif int(current.attempts or 0) >= MAX_DELIVERY_ATTEMPTS:
            current.status = "failed"
            current.last_error = str(result.get("error") or "callback delivery failed")[:2000]
        else:
            current.status = "queued"
            current.last_error = str(result.get("error") or "callback delivery failed")[:2000]
            delay = DELIVERY_BACKOFF_SECONDS[min(int(current.attempts or 1) - 1, len(DELIVERY_BACKOFF_SECONDS) - 1)]
            current.next_attempt_at = now + timedelta(seconds=delay)
        await db.commit()
    return result


async def enqueue_public_callback_delivery(*, kind: str, run_id: str, tenant_id: str, callback_url: str, payload: dict[str, Any]) -> str:
    """Upsert one terminal callback and attempt it once without losing the outbox."""
    callback_url = validate_public_callback_url(callback_url)
    if not callback_url:
        return ""
    async with AdminSessionLocal() as db:
        row = await db.scalar(
            select(PublicCallbackDelivery).where(
                PublicCallbackDelivery.tenant_id == tenant_id,
                PublicCallbackDelivery.kind == kind,
                PublicCallbackDelivery.run_id == run_id,
            )
        )
        if not row:
            row = PublicCallbackDelivery(tenant_id=tenant_id, kind=kind, run_id=run_id, callback_url=callback_url, payload_json=payload)
            db.add(row)
            await db.flush()
        elif row.status != "succeeded":
            row.callback_url = callback_url
            row.payload_json = payload
            row.status = "queued"
            row.next_attempt_at = utcnow()
            row.last_error = ""
        delivery_id = row.id
        await db.commit()
    try:
        await deliver_public_callback_delivery(delivery_id)
    except Exception:
        logger.exception("public callback outbox attempt failed delivery_id=%s", delivery_id)
    return delivery_id


async def deliver_due_public_callbacks(limit: int = 20) -> int:
    """Drain due callbacks; stale leases are reclaimable after a worker crash."""
    now = utcnow()
    async with AdminSessionLocal() as db:
        rows = (
            await db.execute(
                select(PublicCallbackDelivery.id)
                .where(
                    PublicCallbackDelivery.next_attempt_at <= now,
                    or_(
                        PublicCallbackDelivery.status == "queued",
                        (PublicCallbackDelivery.status == "sending") & (PublicCallbackDelivery.lease_until < now),
                    ),
                )
                .order_by(PublicCallbackDelivery.next_attempt_at)
                .limit(max(1, min(limit, 100)))
            )
        ).all()
    for (delivery_id,) in rows:
        await deliver_public_callback_delivery(delivery_id)
    return len(rows)
