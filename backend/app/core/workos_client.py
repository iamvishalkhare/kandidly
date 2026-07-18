"""WorkOS SDK client (AuthKit hosted-UI redirect flow). Kept in its own module
so tests can monkeypatch `get_client` without touching the auth routes."""

from __future__ import annotations

from functools import lru_cache

from workos import WorkOSClient

from app.core.config import settings
from app.core.errors import AppError


@lru_cache
def get_client() -> WorkOSClient:
    if not settings.workos_api_key or not settings.workos_client_id:
        raise AppError("internal_error", "WorkOS is not configured")
    return WorkOSClient(api_key=settings.workos_api_key, client_id=settings.workos_client_id)
