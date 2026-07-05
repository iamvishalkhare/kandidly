"""Application lifecycle. The single authorized write path for
`applications.state` (SPEC §7 write-path rule 1): in ONE transaction it
(a) updates state, (b) merges {to_state: now()} into state_timestamps,
(c) inserts an application_events row. No other code may mutate state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.ids import new_id
from app.db.models import Application, ApplicationEvent, FormSubmission
from app.domain.states import APPLICATION_INITIAL, assert_application_transition

Actor = str  # 'candidate' | 'system' | 'admin' | 'agent'


async def create_application(
    session: AsyncSession,
    *,
    requisition_id: UUID,
    candidate_id: UUID,
    invite_link_id: UUID,
    template_id: UUID,
) -> Application:
    """Insert a fresh application in the initial state with its empty
    form_submission, and log the creation event (SPEC §8.2 first row). This is
    the only initial-insert path; all subsequent changes go through transition()."""
    now = datetime.now(UTC)
    app = Application(
        id=new_id(),
        requisition_id=requisition_id,
        candidate_id=candidate_id,
        invite_link_id=invite_link_id,
        state=APPLICATION_INITIAL,
        state_timestamps={APPLICATION_INITIAL: now.isoformat()},
    )
    session.add(app)
    await session.flush()  # assign PK so the submission can reference it

    submission = FormSubmission(
        id=new_id(),
        application_id=app.id,
        template_id=template_id,
    )
    session.add(submission)
    await session.flush()
    app.form_submission_id = submission.id

    session.add(
        ApplicationEvent(
            application_id=app.id,
            from_state=None,
            to_state=APPLICATION_INITIAL,
            actor="system",
            meta={"invite_link_id": str(invite_link_id)},
        )
    )
    return app


async def transition(
    session: AsyncSession,
    app_id: UUID,
    to_state: str,
    actor: Actor,
    meta: dict | None = None,
) -> Application:
    """Validate + apply an application state transition. Caller owns commit."""
    app = await session.get(Application, app_id, with_for_update=True)
    if app is None:
        raise AppError("not_found", "Application not found", detail={"application_id": str(app_id)})

    frm = app.state
    if frm == to_state:
        # Idempotent no-op for re-delivered events; do not double-log.
        return app

    assert_application_transition(frm, to_state)

    now = datetime.now(UTC)
    app.state = to_state
    # JSONB merge in app code; reassign so SQLAlchemy flags the column dirty.
    stamps = dict(app.state_timestamps or {})
    stamps[to_state] = now.isoformat()
    app.state_timestamps = stamps
    app.updated_at = now

    session.add(
        ApplicationEvent(
            application_id=app_id,
            from_state=frm,
            to_state=to_state,
            actor=actor,
            meta=meta or {},
        )
    )
    return app


async def get_owned(session: AsyncSession, app_id: UUID, candidate_id: UUID) -> Application:
    """Fetch an application, enforcing candidate ownership (SPEC §16.3)."""
    app = await session.get(Application, app_id)
    if app is None:
        raise AppError("not_found", "Application not found")
    if app.candidate_id != candidate_id:
        raise AppError("forbidden", "Not your application")
    return app


async def find_live_application(
    session: AsyncSession, requisition_id: UUID, candidate_id: UUID
) -> Application | None:
    """Return the candidate's non-terminal application for a requisition, if any
    (mirrors the uq_app_live partial unique index, SPEC §7.6)."""
    stmt = select(Application).where(
        Application.requisition_id == requisition_id,
        Application.candidate_id == candidate_id,
        Application.state.notin_(("abandoned", "expired")),
    )
    return (await session.execute(stmt)).scalar_one_or_none()
