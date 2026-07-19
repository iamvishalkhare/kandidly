"""JIT user provisioning from a WorkOS AuthKit login. Candidate signup is
open; console signup only happens for emails that already passed the
invite-only allowlist gate (domain/access.py, checked in api/auth.py).

Match order: `users.workos_user_id`, else email (links pre-WorkOS seeded/dev
rows by stamping their workos_user_id), else create. New *console* signups get
their OWN fresh Organization (they must never land in the seeded default org —
the upcoming orgs feature builds on this); new *candidate* signups stay
org-less, mirroring the seeded candidates. Orgs are app-DB-only: we never
create WorkOS organizations.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.db.models import Organization, User

Intent = Literal["console", "candidate"]


class WorkOSUserLike(Protocol):
    """The slice of workos.types.user_management.User we consume (structural,
    so tests can pass a plain stub)."""

    id: str
    email: str
    first_name: str | None
    last_name: str | None
    profile_picture_url: str | None


@dataclass(frozen=True)
class ProvisionResult:
    user: User
    created: bool


def _display_name(wuser: WorkOSUserLike) -> str | None:
    parts = [p for p in (wuser.first_name, wuser.last_name) if p]
    return " ".join(parts) or None


def _org_seed(wuser: WorkOSUserLike) -> tuple[str, str]:
    """(name, slug) for a fresh signup's own org — refined later by the orgs
    feature; the slug's random suffix keeps the unique constraint safe."""
    base = _display_name(wuser) or wuser.email.split("@", 1)[0]
    slug_base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "org"
    return f"{base}'s Organization", f"{slug_base}-{secrets.token_hex(3)}"


async def provision_workos_user(
    db: AsyncSession, wuser: WorkOSUserLike, intent: Intent
) -> ProvisionResult:
    user = (
        await db.execute(select(User).where(User.workos_user_id == wuser.id))
    ).scalar_one_or_none()
    created = False

    if user is None:
        user = (
            await db.execute(select(User).where(func.lower(User.email) == wuser.email.lower()))
        ).scalar_one_or_none()
        if user is not None:
            user.workos_user_id = wuser.id

    if user is None:
        created = True
        if intent == "candidate":
            org_id = None
            role = "candidate"
        else:
            name, slug = _org_seed(wuser)
            org = Organization(id=new_id(), name=name, slug=slug)
            db.add(org)
            # Flush before the User row references org.id (no relationship()s,
            # so SQLAlchemy cannot order the inserts itself).
            await db.flush()
            org_id = org.id
            role = "admin"
        user = User(
            id=new_id(),
            email=wuser.email,
            role=role,
            org_id=org_id,
            workos_user_id=wuser.id,
            status="active",
        )
        db.add(user)
        await db.flush()

    # Refresh profile data on every login (name/photo can change upstream).
    display = _display_name(wuser)
    if display:
        user.display_name = display
    if wuser.profile_picture_url:
        user.avatar_url = wuser.profile_picture_url
    return ProvisionResult(user=user, created=created)
