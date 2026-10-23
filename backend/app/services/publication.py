"""Reliable, signed publication-channel delivery."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from ..config import get_settings
from ..db import ControllerSessionLocal
from ..models import PublishBinding, PublishChannel, PublishDelivery


def now() -> datetime:
    return datetime.now(timezone.utc)


def channel_payload(code: str, event: dict) -> dict:
    text = f"AI 中台资源已发布：{event['resource_type']} v{event['version']}"
    if code == "feishu":
        return {"msg_type": "text", "content": {"text": text}, "event": event}
    if code == "dingtalk":
        return {"msgtype": "text", "text": {"content": text}, "event": event}
    if code in {"wecom", "wechat"}:
        return {"msgtype": "text", "text": {"content": text}, "event": event}
    return event


def signed_headers(payload: dict, secret: str, timestamp: str) -> dict[str, str]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    return {"X-AI-Event": "resource.published", "X-AI-Timestamp": timestamp, "X-AI-Signature": f"sha256={signature}"}


async def deliver(delivery_id: str) -> None:
    settings = get_settings()
    async with ControllerSessionLocal() as db:
        result = await db.execute(
            select(PublishDelivery, PublishBinding, PublishChannel)
            .join(PublishBinding, PublishBinding.id == PublishDelivery.binding_id)
            .join(PublishChannel, PublishChannel.id == PublishBinding.channel_id)
            .where(PublishDelivery.id == delivery_id)
        )
        pair = result.first()
        if not pair:
            return
        delivery, binding, channel = pair
        if delivery.status == "delivered":
            return
        config = {**(channel.config_json or {}), **(binding.config_json or {})}
        webhook_url = str(config.get("webhook_url") or "")
        if channel.code not in {"feishu", "wecom", "wechat", "dingtalk", "a2a"}:
            delivery.status = "delivered"
            delivery.delivered_at = now()
            binding.status = "published"
            binding.published_at = delivery.delivered_at
            await db.commit()
            return
        parsed = urlparse(webhook_url)
        delivery.status = "delivering"
        delivery.attempt_count += 1
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.hostname.lower() not in settings.allowed_hosts:
            delivery.status, delivery.error = "dead", "发布渠道地址不在 HTTP 白名单中"
            delivery.next_attempt_at = now() + timedelta(minutes=30)
            await db.commit()
            return
        payload = channel_payload(channel.code, delivery.payload_json or {})
        timestamp = str(int(now().timestamp()))
        secret = settings.publication_signing_secret
        headers = signed_headers(payload, secret, timestamp) if secret else {"X-AI-Event": "resource.published", "X-AI-Timestamp": timestamp}
        await db.commit()
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await client.post(webhook_url, json=payload, headers=headers)
                response.raise_for_status()
            delivery.status = "delivered"
            delivery.response_json = {"status_code": response.status_code, "body": response.text[:2000]}
            delivery.error = ""
            delivery.delivered_at = now()
            delivery.next_attempt_at = None
            binding.status = "published"
            binding.published_at = delivery.delivered_at
            await db.commit()
        except Exception as exc:
            delivery.status = "dead" if delivery.attempt_count >= settings.worker_max_attempts else "failed"
            delivery.error = f"{type(exc).__name__}: {exc}"[:2000]
            delivery.next_attempt_at = now() + timedelta(seconds=min(30 * (2 ** max(delivery.attempt_count - 1, 0)), 1800))
            await db.commit()
