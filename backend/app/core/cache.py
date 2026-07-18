"""Redis JSON cache for hot-path reads (SPEC §9). A single lazily-created
`redis.asyncio` client (mirrors the pool style in app/core/ratelimit.py). Used
to cache the interview context bundle so room-load reads are one key lookup
instead of several Postgres queries + re-assembly."""

from __future__ import annotations

import json
from typing import Any

_pool = None


async def _get_redis():
    global _pool
    if _pool is None:
        from redis.asyncio import Redis

        from app.core.config import settings

        _pool = Redis.from_url(settings.redis_url, decode_responses=True)
    return _pool


async def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    r = await _get_redis()
    data = json.dumps(value, default=str)
    if ttl:
        await r.set(key, data, ex=ttl)
    else:
        await r.set(key, data)


async def delete(key: str) -> None:
    r = await _get_redis()
    await r.delete(key)


async def get_json(key: str) -> Any | None:
    r = await _get_redis()
    raw = await r.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None
