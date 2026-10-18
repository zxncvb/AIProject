import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

from .config import get_settings


password_hash = PasswordHash.recommended()
settings = get_settings()


def hash_password(value: str) -> str:
    return password_hash.hash(value)


def verify_password(value: str, encoded: str) -> bool:
    return password_hash.verify(value, encoded)


def create_access_token(user_id: str, tenant_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(claims, settings.app_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])


def _fernet() -> Fernet:
    key = settings.app_encryption_key or base64.urlsafe_b64encode(hashlib.sha256(settings.app_secret_key.encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def _vault_headers() -> dict[str, str]:
    if not settings.vault_token:
        raise RuntimeError("Vault token 未配置")
    headers = {"X-Vault-Token": settings.vault_token}
    if settings.vault_namespace:
        headers["X-Vault-Namespace"] = settings.vault_namespace
    return headers


def _vault_url(path: str) -> str:
    return f"{settings.vault_addr.rstrip('/')}/v1/{path.lstrip('/')}"


def _vault_encrypt(value: str) -> str:
    response = httpx.post(
        _vault_url(f"{settings.vault_transit_mount}/encrypt/{settings.vault_transit_key}"),
        headers=_vault_headers(),
        json={"plaintext": base64.b64encode(value.encode()).decode()},
        timeout=15,
    )
    response.raise_for_status()
    ciphertext = response.json()["data"]["ciphertext"]
    return f"vault:{settings.vault_transit_mount}:{settings.vault_transit_key}:{ciphertext}"


def _vault_decrypt(value: str) -> str:
    _, mount, key, ciphertext = value.split(":", 3)
    response = httpx.post(
        _vault_url(f"{mount}/decrypt/{key}"),
        headers=_vault_headers(),
        json={"ciphertext": ciphertext},
        timeout=15,
    )
    response.raise_for_status()
    plaintext = response.json()["data"]["plaintext"]
    return base64.b64decode(plaintext).decode()


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    if settings.secret_backend.lower() == "vault":
        return _vault_encrypt(value)
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith("vault:") or settings.secret_backend.lower() == "vault":
        return _vault_decrypt(value)
    return _fernet().decrypt(value.encode()).decode()


def secret_backend_status() -> dict[str, Any]:
    backend = settings.secret_backend.lower()
    if backend != "vault":
        return {"backend": "fernet", "ready": True, "mode": "application-encrypted"}
    try:
        response = httpx.get(_vault_url("sys/health"), headers=_vault_headers(), timeout=5)
        return {"backend": "vault", "ready": response.is_success, "status_code": response.status_code, "address": settings.vault_addr}
    except (httpx.HTTPError, RuntimeError) as exc:
        return {"backend": "vault", "ready": False, "address": settings.vault_addr, "error": str(exc)}
