"""Audit log helper (SPEC §7.16, §12.1). Mutating admin routes write an
audit_log row; append-only (write-path rule 3)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    meta: dict | None = None,
) -> None:
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
