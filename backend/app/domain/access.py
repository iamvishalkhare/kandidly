"""Console access control: the product is invite-only.

One hardcoded operator account owns the allowlist (explicit product decision —
not a role; no other account can grant access) and is itself always allowed to
sign in. Every other email must be on console_allowlist to complete a
console-intent login. Candidate sign-ins are never gated here — interview
access has its own per-requisition guest lists (domain/invites.py).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import AuthUser
from app.db.models import ConsoleAllowlistEntry

# The single account allowed to manage the allowlist and use the other
# operator-only console surfaces (interview deletion, email smoke test).
OPERATOR_EMAIL = "vishalkhare39@gmail.com"


async def console_login_allowed(db: AsyncSession, email: str) -> bool:
    """May this email sign in with console intent? Compared lowercased —
    console_allowlist stores emails lowercased+trimmed."""
    email = email.strip().lower()
    if email == OPERATOR_EMAIL:
        return True
    entry = (
        await db.execute(
            select(ConsoleAllowlistEntry.id).where(ConsoleAllowlistEntry.email == email)
        )
    ).scalar_one_or_none()
    return entry is not None


async def ensure_console_access(db: AsyncSession, user: AuthUser) -> None:
    """Request-time twin of the login gate, run by the staff role guard
    (core/deps.py): a staff session whose email was removed from — or never
    made — the allowlist dies with a 401 on its next API call, so removal
    means "logged out everywhere" without any token bookkeeping. Candidates
    are never gated. Dev tokens skip the check: they only work in the dev
    env, where the seeded staff accounts aren't allowlisted."""
    if user.role not in ("admin", "recruiter") or user.is_dev_token:
        return
    if not await console_login_allowed(db, user.email):
        raise AppError("unauthorized", "Console access has been revoked for this account")
