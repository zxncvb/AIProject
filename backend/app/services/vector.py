from typing import Any

import httpx

from ..config import get_settings
from ..models import ModelProvider
from ..security import decrypt_secret


def collection_name(tenant_id: str, kb_id: str) -> str:
    return f"kb_{tenant_id.replace('-', '')}_{kb_id.replace('-', '')}"


async def embed(provider: ModelProvider, texts: list[str]) -> list[list[float]]:
    base_url = provider.base_url.rstrip("/")
    endpoint = base_url if base_url.endswith("/embeddings") else f"{base_url}/embeddings"
    headers = {"Content-Type": "application/json"}
    api_key = decrypt_secret(provider.api_key_encrypted)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=get_settings().model_timeout_seconds) as client:
        response = await client.post(endpoint, headers=headers, json={"model": provider.config_json.get("embedding_model", get_settings().embedding_model), "input": texts})
        response.raise_for_status()
        data = response.json()
    return [item["embedding"] for item in sorted(data.get("data", []), key=lambda item: item.get("index", 0))]


def vector_size(provider: ModelProvider) -> int:
    configured = (provider.config_json or {}).get("embedding_dimensions")
    try:
        return int(configured or get_settings().qdrant_vector_size)
    except (TypeError, ValueError):
        return get_settings().qdrant_vector_size


async def ensure_collection(name: str, size: int) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{settings.qdrant_url.rstrip('/')}/collections/{name}")
        if response.status_code == 200:
            return
        response = await client.put(f"{settings.qdrant_url.rstrip('/')}/collections/{name}", json={"vectors": {"size": size, "distance": "Cosine"}})
        response.raise_for_status()


async def upsert_chunks(provider: ModelProvider, tenant_id: str, kb_id: str, chunks: list[dict[str, Any]]) -> int:
    if not chunks:
        return 0
    vectors = await embed(provider, [item["content"] for item in chunks])
    if not vectors:
        return 0
    settings = get_settings()
    name = collection_name(tenant_id, kb_id)
    await ensure_collection(name, vector_size(provider))
    points = [{"id": item["id"], "vector": vector, "payload": {"chunk_id": item["id"], "document_id": item["document_id"], "content": item["content"]}} for item, vector in zip(chunks, vectors)]
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.put(f"{settings.qdrant_url.rstrip('/')}/collections/{name}/points?wait=true", json={"points": points})
        response.raise_for_status()
    return len(points)


async def search_vectors(provider: ModelProvider, tenant_id: str, kb_id: str, query: str, limit: int) -> list[dict[str, Any]]:
    vector = (await embed(provider, [query]))[0]
    settings = get_settings()
    name = collection_name(tenant_id, kb_id)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{settings.qdrant_url.rstrip('/')}/collections/{name}/points/search", json={"vector": vector, "limit": limit, "with_payload": True})
        if response.status_code == 404:
            return []
        response.raise_for_status()
        rows = response.json().get("result", [])
    return [{"score": round(float(row.get("score", 0)), 6), **(row.get("payload") or {})} for row in rows]


async def delete_document_vectors(tenant_id: str, kb_id: str, document_id: str) -> None:
    settings = get_settings()
    name = collection_name(tenant_id, kb_id)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{settings.qdrant_url.rstrip('/')}/collections/{name}/points/delete?wait=true", json={"filter": {"must": [{"key": "document_id", "match": {"value": document_id}}]}})
        if response.status_code not in {200, 404}:
            response.raise_for_status()
