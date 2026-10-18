import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DocumentChunk
from ..models import ModelProvider
from .vector import search_vectors


def _terms(query: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[\w\u4e00-\u9fff]{2,}", query)]


async def search_chunks(db: AsyncSession, tenant_id: str, kb_id: str, query: str, limit: int = 5, mode: str = "hybrid") -> list[dict[str, Any]]:
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.kb_id == kb_id).limit(5000)
    )
    terms = _terms(query)
    scored: list[tuple[int, DocumentChunk]] = []
    for row in result.scalars():
        text = row.content.lower()
        score = sum(text.count(term) for term in terms)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    lexical = [{"score": score, "chunk_id": row.id, "document_id": row.document_id, "content": row.content, "source": "keyword"} for score, row in scored[:limit]]
    if mode == "keyword":
        return lexical
    provider = await db.scalar(select(ModelProvider).where(ModelProvider.tenant_id == tenant_id, ModelProvider.enabled.is_(True)).order_by(ModelProvider.created_at))
    if not provider:
        return lexical
    try:
        vector_rows = await search_vectors(provider, tenant_id, kb_id, query, limit)
    except Exception:
        return lexical
    merged: dict[str, dict[str, Any]] = {row["chunk_id"]: row for row in lexical}
    for row in vector_rows:
        chunk_id = row.get("chunk_id")
        if not chunk_id:
            continue
        if chunk_id in merged:
            merged[chunk_id]["score"] = round(float(merged[chunk_id]["score"]) + float(row["score"]), 6)
            merged[chunk_id]["source"] = "hybrid"
        else:
            merged[chunk_id] = {"score": row["score"], "chunk_id": chunk_id, "document_id": row.get("document_id", ""), "content": row.get("content", ""), "source": "vector"}
    return sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:limit]
