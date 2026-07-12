"""Auth session routes. The identity provider is external (SPEC §3.6); the one
thing the backend owns is ending a session: logout denylists the presented
bearer token (Redis, TTL-bound) so it stops authenticating even before it
expires, and leaves an audit trail.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import AuthUser, revoke_token
from app.domain.audit import record_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/logout")
async def logout(
    user: AuthUser = Depends(get_current_user),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = authorization.split(" ", 1)[1].strip() if authorization else ""
    if token:
        await revoke_token(token)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="user.logout",
        entity_type="user",
        entity_id=user.user_id,
    )
    return {"ok": True}
