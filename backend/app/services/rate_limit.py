"""Small in-process fallback for request throttling when Redis is unavailable."""

import asyncio
import time


_buckets: dict[str, tuple[int, float]] = {}
_lock = asyncio.Lock()


async def allow_local(key: str, limit: int, window_seconds: int = 60) -> bool:
    """Return whether the request fits the local fixed-window fallback."""
    now = time.monotonic()
    window = max(1, int(window_seconds))
    max_count = max(1, int(limit))
    async with _lock:
        if len(_buckets) > 10000:
            expired = [bucket_key for bucket_key, (_, expires_at) in _buckets.items() if expires_at <= now]
            for bucket_key in expired:
                _buckets.pop(bucket_key, None)
        count, expires_at = _buckets.get(key, (0, now + window))
        if expires_at <= now:
            count, expires_at = 0, now + window
        count += 1
        _buckets[key] = (count, expires_at)
        return count <= max_count


def clear_local() -> None:
    """Test/support hook; production callers normally let windows expire."""
    _buckets.clear()
