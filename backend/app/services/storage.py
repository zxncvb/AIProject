"""Tenant-scoped artifact storage with local and S3-compatible backends."""

import asyncio
import mimetypes
from pathlib import Path
from typing import Any

from ..config import get_settings


def _local_path(key: str) -> Path:
    root = get_settings().artifact_path.resolve()
    target = (root / "objects" / key).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("storage key escapes artifact directory") from exc
    return target


def _s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("S3 存储需要安装 boto3") from exc
    settings = get_settings()
    kwargs: dict[str, Any] = {"region_name": settings.s3_region or None}
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    if settings.s3_access_key_id:
        kwargs["aws_access_key_id"] = settings.s3_access_key_id
    if settings.s3_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
    return boto3.client("s3", **kwargs)


def backend_name() -> str:
    backend = get_settings().storage_backend.strip().lower()
    if backend not in {"local", "s3"}:
        raise RuntimeError("STORAGE_BACKEND 必须是 local 或 s3")
    if backend == "s3" and not get_settings().s3_bucket:
        raise RuntimeError("S3 存储必须配置 S3_BUCKET")
    return backend


def object_key(tenant_id: str, checksum: str, filename: str) -> str:
    safe_name = Path(filename or "upload.bin").name.replace(" ", "_")[:160]
    return f"tenants/{tenant_id}/documents/{checksum}/{safe_name}"


async def put_bytes(key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
    backend = backend_name()
    if backend == "local":
        path = _local_path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        return backend

    settings = get_settings()
    client = _s3_client()
    await asyncio.to_thread(client.put_object, Bucket=settings.s3_bucket, Key=key, Body=content, ContentType=content_type)
    return backend


async def get_bytes(key: str) -> bytes:
    backend = backend_name()
    if backend == "local":
        path = _local_path(key)
        return await asyncio.to_thread(path.read_bytes)
    settings = get_settings()
    response = await asyncio.to_thread(_s3_client().get_object, Bucket=settings.s3_bucket, Key=key)
    return await asyncio.to_thread(response["Body"].read)


async def delete_object(key: str) -> None:
    if not key:
        return
    backend = backend_name()
    if backend == "local":
        path = _local_path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)
        return
    settings = get_settings()
    await asyncio.to_thread(_s3_client().delete_object, Bucket=settings.s3_bucket, Key=key)


async def presign_get(key: str, filename: str = "download.bin", content_type: str = "application/octet-stream") -> str:
    backend = backend_name()
    if backend == "local":
        return ""
    settings = get_settings()
    client = _s3_client()
    safe_filename = Path(filename).name.replace('"', "_")[:180]
    return await asyncio.to_thread(
        client.generate_presigned_url,
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ResponseContentType": content_type, "ResponseContentDisposition": f'attachment; filename="{safe_filename}"'},
        ExpiresIn=max(60, min(settings.s3_presign_expire_seconds, 86400)),
    )


def content_type_for(filename: str, fallback: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(filename)[0] or fallback
