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
        snapshot_interval_s=settings.snapshot_interval_s,
        livekit_url=settings.livekit_url,
        recaptcha_site_key=settings.recaptcha_site_key,
    )


@router.get("/dev-users")
async def dev_users(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Dev-mode only: list seeded users with ready-made debug bearer tokens so
    the web app can offer a role switcher. 404s outside AUTH_DEV_MODE."""
    import base64
    import json
    from datetime import UTC, datetime

    from sqlalchemy import select as sa_select

    from app.core.errors import AppError
    from app.db.models import User

    if not settings.auth_dev_mode:
        raise AppError("not_found", "Not available")
    users = (await db.execute(sa_select(User).order_by(User.role, User.email))).scalars().all()
    out = []
    for u in users:
        # `iat` makes each issued token unique, so revoking one at logout
        # (auth denylist) doesn't lock the dev user out of the next login.
        payload = {
            "user_id": str(u.id),
            "email": u.email,
            "role": u.role,
            "iat": datetime.now(UTC).isoformat(),
        }
        token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        out.append({"email": u.email, "role": u.role, "token": token})
    return out


@router.post("/dev-reset")
async def dev_reset(body: dict, db: AsyncSession = Depends(get_db)) -> dict:
    """Dev-only helper: abandon a candidate's current application for a link so
    the next claim starts a fresh interview run (no stale 'completed' resume).
    Returns {reset: 0|1}. 404s outside AUTH_DEV_MODE."""
    from sqlalchemy import func as safunc

    from app.core.errors import AppError
    from app.db.models import User
    from app.domain import applications as apps

    if not settings.auth_dev_mode:
        raise AppError("not_found", "Not available")
    token = (body or {}).get("token")
    email = (body or {}).get("email")
    link = (
        await db.execute(select(InviteLink).where(InviteLink.token == token))
    ).scalar_one_or_none()
    user = (
        (await db.execute(select(User).where(safunc.lower(User.email) == email.lower()))).scalar_one_or_none()
        if email
        else None
    )
    if link is None or user is None:
        return {"reset": 0}
    live = await apps.find_live_application(db, link.requisition_id, user.id)
    if live is None:
        return {"reset": 0}
    # Drops out of the uq_app_live partial index, so the next claim makes a new
    # application. Direct set is a deliberate dev-only shortcut past transition().
    live.state = "abandoned"
    return {"reset": 1}


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
        # Landing-page views; use_count counts claims (registrations).
        link.click_count = (link.click_count or 0) + 1

    res = resolve(link, requisition)
    return LinkResolveOut(
        title=requisition.title if requisition else None,
        interview_type=requisition.interview_type if requisition else None,
        status_ok=res.status_ok,
        reason=res.reason,
    )
