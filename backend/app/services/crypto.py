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
