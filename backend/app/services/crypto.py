import hashlib


def checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def chunk_text(text: str, size: int = 1200, overlap: int = 160) -> list[str]:
    clean = "\n".join(line.strip() for line in text.replace("\r", "").split("\n") if line.strip())
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def chunk_text_configured(
    text: str,
    *,
    mode: str = "auto",
    size: int = 1200,
    overlap: int = 160,
    separator: str = "\n\n",
) -> list[str]:
    """Split knowledge content using the platform or an explicit separator."""
    if mode == "auto":
        return chunk_text(text, size=size, overlap=overlap)
    if mode != "custom":
        raise ValueError("chunking mode must be auto or custom")
    separator = separator[:32]
    if not separator:
        raise ValueError("custom chunk separator cannot be empty")
    clean = "\n".join(line.strip() for line in text.replace("\r", "").split("\n") if line.strip())
    parts = [part.strip() for part in clean.split(separator) if part.strip()]
    if not parts:
        return []
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(part) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(chunk_text(part, size=size, overlap=overlap))
            continue
        candidate = f"{current}{separator}{part}" if current else part
        if current and len(candidate) > size:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}{separator}{part}" if tail else part
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
