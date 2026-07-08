"""Audit log helper (SPEC §7.16, §12.1). Mutating admin routes write an
audit_log row; append-only (write-path rule 3)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, User


async def record_audit(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    meta: dict | None = None,
) -> None:
    # actor_id is a nullable FK to users.id. A dev/stale bearer token can carry
    # a user id with no matching row (the same tolerance _org_id_for grants when
    # resolving the org); a best-effort audit write must never turn that into an
    # FK violation that rolls back the whole request's writes. Fall back to a
    # null actor when the referenced user is absent.
    if actor_id is not None and await session.get(User, actor_id) is None:
        actor_id = None
    # audit_log.id is a BIGSERIAL — let the database assign it (a UUID here
    # fails asyncpg's int64 bind at commit time, silently rolling back the
    # whole request's writes after the 200 has been sent).
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            meta=meta or {},
        )
    )
