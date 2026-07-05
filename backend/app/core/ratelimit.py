"""Rate limiting (SPEC §12.5). Redis fixed-window counters; returns
429 {"code":"rate_limited"} via the standard envelope. Dependency factory:

    @router.post("/claim", dependencies=[rate_limit("claim", 10)])

Keys are per-user (authed routes) or per-IP (public routes), per minute window.
Fails open if Redis is unreachable — availability over strictness in v1.
"""

from __future__ import annotations

import time

from fastapi import Depends, Request

from app.core.errors import AppError


async def _redis():
    from redis.asyncio import Redis

    from app.core.config import settings

    return Redis.from_url(settings.redis_url, decode_responses=True)


_pool = None


async def _get_redis():
    global _pool
    if _pool is None:
        _pool = await _redis()
    return _pool


def rate_limit(name: str, per_minute: int, *, by: str = "auto"):
    """Dependency enforcing `per_minute` requests per identity per fixed
    minute window. `by`: 'auto' (user if authed else IP), 'ip', or 'user'."""

    async def _dep(request: Request) -> None:
        # Identity: bearer token hash when present, else client IP.
        ident = None
        if by in ("auto", "user"):
            auth = request.headers.get("authorization", "")
            if auth:
                ident = f"u:{hash(auth) & 0xFFFFFFFF:x}"
        if ident is None:
            fwd = request.headers.get("x-forwarded-for")
            ip = (
                fwd.split(",")[0].strip()
                if fwd
                else (request.client.host if request.client else "unknown")
            )
            ident = f"ip:{ip}"

        window = int(time.time() // 60)
        key = f"rl:{name}:{ident}:{window}"
        try:
            r = await _get_redis()
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, 90)
        except Exception:  # noqa: BLE001 — fail open
            return
        if count > per_minute:
            raise AppError(
                "rate_limited",
                f"Rate limit exceeded for {name}",
                detail={"limit_per_minute": per_minute},
            )

    return Depends(_dep)
