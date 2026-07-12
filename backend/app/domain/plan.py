"""Free-plan quota checks. Usage is counted per org: requisitions ever
created, and interviews ever started (cumulative — an Interview row is created
at form submit, so every candidate attempt counts).

Two thresholds gate the product:
- free_plan_max_requisitions: the console refuses to deploy new requisitions
  past this (upgrade prompt).
- free_plan_interview_hold_at: candidate attempts are refused with ER0402
  ("interview on hold") once the org's cumulative interview count reaches it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Interview, Requisition

# Stable, user-facing error code for the candidate-side hold (surfaced in the
# error envelope's detail and shown on the landing page).
INTERVIEW_HOLD_ERROR_CODE = "ER0402"


async def requisition_count(db: AsyncSession, org_id: UUID) -> int:
    # Soft-deleted requisitions free their quota slot (their interviews still
    # count toward the cumulative interview quota below).
    return (
        await db.execute(
            select(func.count())
            .select_from(Requisition)
            .where(Requisition.org_id == org_id, Requisition.deleted_at.is_(None))
        )
    ).scalar_one()


async def interview_count(db: AsyncSession, org_id: UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Interview)
            .join(Requisition, Requisition.id == Interview.requisition_id)
            .where(Requisition.org_id == org_id)
        )
    ).scalar_one()


async def ensure_can_create_requisition(db: AsyncSession, org_id: UUID, *, deploy: bool) -> None:
    """Gate for creating a new requisition (the builder's Deploy / save)."""
    used = await requisition_count(db, org_id)
    if used < settings.free_plan_max_requisitions:
        return
    message = (
        "Please upgrade to deploy more interviews."
        if deploy
        else f"Your free plan allows {settings.free_plan_max_requisitions} requisitions. "
        "Please upgrade to create more."
    )
    raise AppError(
        "plan_limit",
        message,
        detail={
            "limit": settings.free_plan_max_requisitions,
            "used": used,
            "resource": "requisitions",
        },
    )


async def ensure_interview_capacity(db: AsyncSession, org_id: UUID) -> None:
    """Gate for candidate attempts (claim + form submit)."""
    used = await interview_count(db, org_id)
    if used < settings.free_plan_interview_hold_at:
        return
    raise AppError(
        "plan_limit",
        "This interview is on hold. Please contact your recruiter for more details.",
        detail={
            "error_code": INTERVIEW_HOLD_ERROR_CODE,
            "limit": settings.free_plan_interview_hold_at,
            "used": used,
            "resource": "interviews",
        },
    )
