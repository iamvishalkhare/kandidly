"""Public (unauthenticated) API (SPEC §12.2 #1–2, §6.2, §8.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.ratelimit import rate_limit
from app.db.models import InviteLink, Requisition
from app.domain.links import resolve
from app.schemas.api import ConfigOut, LinkResolveOut

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/config", response_model=ConfigOut)
async def get_config() -> ConfigOut:
    return ConfigOut(
        snapshot_min_s=settings.snapshot_min_s,
        snapshot_max_s=settings.snapshot_max_s,
        livekit_url=settings.livekit_url,
    )


@router.get("/dev-users")
async def dev_users(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Dev-mode only: list seeded users with ready-made debug bearer tokens so
    the web app can offer a role switcher. 404s outside AUTH_DEV_MODE."""
    import base64
    import json

    from sqlalchemy import select as sa_select

    from app.core.errors import AppError
    from app.db.models import User

    if not settings.auth_dev_mode:
        raise AppError("not_found", "Not available")
    users = (await db.execute(sa_select(User).order_by(User.role, User.email))).scalars().all()
    out = []
    for u in users:
        payload = {"user_id": str(u.id), "email": u.email, "role": u.role}
        token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        out.append({"email": u.email, "role": u.role, "token": token})
    return out


@router.get(
    "/i/{token}",
    response_model=LinkResolveOut,
    dependencies=[rate_limit("link_resolve", 60, by="ip")],
)
async def resolve_link(token: str, db: AsyncSession = Depends(get_db)) -> LinkResolveOut:
    """Link resolution for the landing page — never 404s (SPEC §13.2.1)."""
    link = (
        await db.execute(select(InviteLink).where(InviteLink.token == token))
    ).scalar_one_or_none()
    requisition = None
    if link is not None:
        requisition = await db.get(Requisition, link.requisition_id)

    res = resolve(link, requisition)
    return LinkResolveOut(
        title=requisition.title if requisition else None,
        interview_type=requisition.interview_type if requisition else None,
        status_ok=res.status_ok,
        reason=res.reason,
    )
