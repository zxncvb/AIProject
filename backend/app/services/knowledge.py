import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Document, DocumentChunk
from ..models import ModelProvider
from .vector import search_vectors


def _terms(query: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[\w\u4e00-\u9fff]{2,}", query)]


def _normalize_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    high = max(values)
    low = min(values)
    if high <= low:
        return [1.0 if high > 0 else 0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def rerank_candidates(candidates: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    """Apply deterministic lexical coverage reranking after hybrid retrieval.

    The reranker is intentionally local and explainable: vector/keyword scores
    provide recall while term coverage and exact phrase matches improve the
    final ordering without sending document content to another service.
    """
    terms = _terms(query)
    phrase = " ".join(terms)
    for item in candidates:
        content = str(item.get("content") or "").lower()
        coverage = sum(1 for term in terms if term in content) / max(1, len(terms))
        phrase_bonus = 0.15 if phrase and phrase in content else 0.0
        item["score"] = round(float(item.get("score", 0)) * 0.8 + coverage * 0.2 + phrase_bonus, 6)
        item["rerank"] = {"term_coverage": round(coverage, 4), "phrase_match": bool(phrase_bonus)}
    return sorted(candidates, key=lambda item: (item["score"], item.get("chunk_id", "")), reverse=True)[:limit]


SEARCH_METADATA_FIELDS = {
    "source": Document.source,
    "mime_type": Document.mime_type,
    "status": Document.status,
    "security_status": Document.security_status,
    "document_id": Document.id,
    "title": Document.title,
}


def normalize_metadata_filter(metadata: dict[str, Any] | None) -> dict[str, str | list[str]]:
    """Keep search filters finite and restricted to document metadata fields."""
    if not metadata:
        return {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata filter must be a JSON object")
    result: dict[str, str | list[str]] = {}
    for key, value in metadata.items():
        if key not in SEARCH_METADATA_FIELDS:
            raise ValueError(f"unsupported metadata filter: {key}")
        if isinstance(value, list):
            values = [str(item).strip() for item in value if str(item).strip()]
            if not values or len(values) > 20:
                raise ValueError(f"metadata filter {key} must contain 1-20 values")
            result[key] = values
        elif isinstance(value, (str, int, float, bool)):
            text = str(value).strip()
            if not text or len(text) > 300:
                raise ValueError(f"metadata filter {key} is too long or empty")
            result[key] = text
        else:
            raise ValueError(f"metadata filter {key} must be scalar or an array")
    return result


async def search_chunks(
    db: AsyncSession,
    tenant_id: str,
    kb_id: str,
    query: str,
    limit: int = 5,
    mode: str = "hybrid",
    metadata_filter: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    normalized_filter = normalize_metadata_filter(metadata_filter)
    statement = select(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id).where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.kb_id == kb_id, Document.tenant_id == tenant_id)
    for key, value in normalized_filter.items():
        column = SEARCH_METADATA_FIELDS[key]
        statement = statement.where(column.in_(value) if isinstance(value, list) else column == value)
    result = await db.execute(statement.limit(max(limit * 20, min(get_settings().knowledge_candidate_limit, 50000))))
    terms = _terms(query)
    scored: list[tuple[float, DocumentChunk]] = []
    for row in result.scalars():
        text = row.content.lower()
        score = sum(text.count(term) for term in terms)
        if score:
            scored.append((float(score), row))
    scored.sort(key=lambda item: item[0], reverse=True)
    lexical_scores = _normalize_scores([score for score, _ in scored[: max(limit * 5, limit)]])
    lexical = [{"score": score, "chunk_id": row.id, "document_id": row.document_id, "content": row.content, "source": "keyword"} for score, (_, row) in zip(lexical_scores, scored[: max(limit * 5, limit)])]
    if mode == "keyword":
        return rerank_candidates(lexical, query, limit)
    provider = await db.scalar(select(ModelProvider).where(ModelProvider.tenant_id == tenant_id, ModelProvider.enabled.is_(True)).order_by(ModelProvider.created_at))
    if not provider:
        return rerank_candidates(lexical, query, limit)
    try:
        vector_rows = await search_vectors(provider, tenant_id, kb_id, query, limit)
    except Exception:
        return rerank_candidates(lexical, query, limit)
    vector_scores = _normalize_scores([float(row.get("score", 0)) for row in vector_rows])
    merged: dict[str, dict[str, Any]] = {row["chunk_id"]: row for row in lexical}
    for row, normalized_score in zip(vector_rows, vector_scores):
        chunk_id = row.get("chunk_id")
        if not chunk_id:
            continue
        if chunk_id in merged:
            merged[chunk_id]["score"] = round(float(merged[chunk_id]["score"]) * 0.45 + normalized_score * 0.55, 6)
            merged[chunk_id]["source"] = "hybrid"
        else:
            merged[chunk_id] = {"score": round(normalized_score, 6), "chunk_id": chunk_id, "document_id": row.get("document_id", ""), "content": row.get("content", ""), "source": "vector"}
    return rerank_candidates(list(merged.values()), query, limit)
