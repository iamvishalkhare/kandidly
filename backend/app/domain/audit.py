"""Audit log helper (SPEC §7.16, §12.1). Mutating admin routes write an
audit_log row; append-only (write-path rule 3)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
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
    session.add(
        AuditLog(
            id=new_id(),
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            meta=meta or {},
        )
    )
