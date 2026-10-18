from typing import Any

import httpx

from ..config import get_settings


async def send_alert(title: str, text: str, severity: str = "warning", target: str = "generic") -> dict[str, Any]:
    settings = get_settings()
    urls = {
        "generic": settings.alert_webhook_url,
        "dingtalk": settings.alert_dingtalk_webhook_url,
        "feishu": settings.alert_feishu_webhook_url,
        "wecom": settings.alert_wecom_webhook_url,
    }
    url = urls.get(target, "")
    if not url:
        return {"sent": False, "target": target, "reason": "webhook_not_configured"}
    if target == "dingtalk":
        payload = {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n> {severity}\n\n{text}"}}
    elif target == "feishu":
        payload = {"msg_type": "text", "content": {"text": f"{title}\n[{severity}] {text}"}}
    elif target == "wecom":
        payload = {"msgtype": "markdown", "markdown": {"content": f"## {title}\n> {severity}\n{text}"}}
    else:
        payload = {"title": title, "text": text, "severity": severity}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    return {"sent": True, "target": target, "status_code": response.status_code}
