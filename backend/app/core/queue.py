"""arq enqueue helper (SPEC §3.1, §14). A single shared Redis pool is created
lazily so request handlers can enqueue background jobs by name."""

from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue(job: str, *args: Any, **kwargs: Any) -> None:
    """Enqueue an arq job by function name (see app.jobs.worker.WorkerSettings)."""
    pool = await get_pool()
    await pool.enqueue_job(job, *args, **kwargs)
