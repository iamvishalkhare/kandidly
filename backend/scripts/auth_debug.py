"""Ops diagnostic (ops.yml `auth-debug`): print everything sign-in-relevant
about an email as JSON — the users row, console_allowlist entries, requisition
invites, and recent auth/allowlist audit entries — so "this email can't log
in" can be diagnosed from outside the box without DB access.

Run inside the backend container:
    env PYTHONPATH=/app/backend /app/.venv/bin/python \
        /app/backend/scripts/auth_debug.py <email>
"""

from __future__ import annotations

import asyncio
import json
import sys


async def main(email: str) -> None:
    from sqlalchemy import func, select

    from app.db.models import AuditLog, ConsoleAllowlistEntry, RequisitionInvite, User
    from app.db.session import SessionLocal
    from app.domain.access import OPERATOR_EMAIL

    email = email.strip().lower()
    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(func.lower(User.email) == email))
        ).scalar_one_or_none()
        allow = (
            (
                await db.execute(
                    select(ConsoleAllowlistEntry).where(ConsoleAllowlistEntry.email == email)
                )
            )
            .scalars()
            .all()
        )
        invites = (
            (await db.execute(select(RequisitionInvite).where(RequisitionInvite.email == email)))
            .scalars()
            .all()
        )
        audits = []
        if user is not None:
            audits = (
                (
                    await db.execute(
                        select(AuditLog)
                        .where(AuditLog.actor_id == user.id)
                        .order_by(AuditLog.created_at.desc())
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )

    out = {
        "email": email,
        "is_operator": email == OPERATOR_EMAIL,
        "user": None
        if user is None
        else {
            "id": str(user.id),
            "role": user.role,
            "status": user.status,
            "org_id": str(user.org_id) if user.org_id else None,
            "workos_user_id": user.workos_user_id,
            "display_name": user.display_name,
            "created_at": str(user.created_at),
        },
        "console_allowlist": [{"id": str(a.id), "created_at": str(a.created_at)} for a in allow],
        "requisition_invites": [
            {"requisition_id": str(i.requisition_id), "created_at": str(i.created_at)}
            for i in invites
        ],
        "recent_audit": [{"action": a.action, "at": str(a.created_at)} for a in audits],
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
