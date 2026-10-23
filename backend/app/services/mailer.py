"""Minimal SMTP delivery used by password reset and invitation workflows."""

import asyncio
import smtplib
from email.message import EmailMessage

from ..config import get_settings


def _send(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP 尚未配置")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


async def send_email(to: str, subject: str, body: str) -> None:
    await asyncio.to_thread(_send, to, subject, body)
