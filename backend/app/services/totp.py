import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def random_base32(length: int = 20) -> str:
    return base64.b32encode(secrets.token_bytes(length)).decode("ascii").rstrip("=")


def code(secret: str, timestamp: int | None = None) -> str:
    timestamp = int(time.time()) if timestamp is None else int(timestamp)
    counter = timestamp // 30
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify(secret: str, value: str, window: int = 1) -> bool:
    current = int(time.time())
    return any(hmac.compare_digest(code(secret, current + step * 30), str(value)) for step in range(-window, window + 1))


def provisioning_uri(secret: str, account: str, issuer: str = "Enterprise AI Platform") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
