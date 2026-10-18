import json
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt

from ..config import get_settings


class OIDCError(RuntimeError):
    pass


def _settings():
    settings = get_settings()
    if not settings.oidc_issuer_url or not settings.oidc_client_id or not settings.oidc_client_secret:
        raise OIDCError("OIDC 尚未配置")
    return settings


async def discovery() -> dict[str, Any]:
    settings = _settings()
    issuer = settings.oidc_issuer_url.rstrip("/")
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(f"{issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        return response.json()


async def create_authorization_url(tenant_slug: str) -> tuple[str, str]:
    settings = _settings()
    document = await discovery()
    state = uuid4().hex + uuid4().hex
    nonce = uuid4().hex
    query = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes,
        "state": state,
        "nonce": nonce,
        "tenant": tenant_slug,
    }
    return f"{document['authorization_endpoint']}?{urlencode(query)}", json.dumps({"tenant_slug": tenant_slug, "nonce": nonce})


async def exchange_code(code: str, expected_nonce: str) -> dict[str, Any]:
    settings = _settings()
    document = await discovery()
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.post(
            document["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
        )
        response.raise_for_status()
        token_response = response.json()
        id_token = token_response.get("id_token")
        if not id_token:
            raise OIDCError("OIDC 响应缺少 id_token")
        keys_response = await client.get(document["jwks_uri"])
        keys_response.raise_for_status()
        keys = keys_response.json().get("keys", [])

    header = jwt.get_unverified_header(id_token)
    key_data = next((item for item in keys if item.get("kid") == header.get("kid")), None)
    if not key_data:
        raise OIDCError("OIDC 签名密钥不存在")
    claims = jwt.decode(
        id_token,
        key=jwt.PyJWK.from_dict(key_data).key,
        algorithms=[header.get("alg", "RS256")],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer_url.rstrip("/"),
        options={"require": ["sub", "exp", "iss", "aud"]},
    )
    if claims.get("nonce") != expected_nonce:
        raise OIDCError("OIDC nonce 校验失败")
    if not claims.get(get_settings().oidc_email_claim):
        access_token = token_response.get("access_token")
        userinfo_endpoint = document.get("userinfo_endpoint")
        if access_token and userinfo_endpoint:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                userinfo = await client.get(userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"})
                userinfo.raise_for_status()
            claims = {**claims, **userinfo.json()}
    if not claims.get(get_settings().oidc_email_claim):
        raise OIDCError(f"OIDC 身份缺少 {get_settings().oidc_email_claim}")
    return claims
