"""Email jobs. send_email is the generic delivery task: retryable transport
failures (429/5xx/network) back off exponentially via arq Retry; everything
else — rendering errors, rejected payloads, exhausted tries — is logged loudly
and swallowed so a bad email can never become a worker crash loop.

send_invite_email wraps it for requisition_invites rows: it builds the
candidate_invite context from the invite + requisition and records the
delivery outcome on the row (email_status sent/failed)."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from arq import Retry
from sqlalchemy import select

from app.core import email as email_core
from app.core.config import settings
from app.core.queue import enqueue

log = structlog.get_logger(__name__)

MAX_TRIES = 5
_BACKOFF_BASE_S = 30  # 30s, 60s, 120s, 240s between the 5 tries


async def send_email(ctx: dict, to: str, template: str, context: dict) -> str:
    """Returns the terminal outcome ('sent' | 'failed'); raises arq Retry in
    between. Callers that track delivery (send_invite_email) rely on this."""
    job_try = ctx.get("job_try", 1)
    try:
        message_id = await email_core.send(to=to, template=template, context=context)
    except email_core.EmailSendError as exc:
        if exc.retryable and job_try < MAX_TRIES:
            defer = _BACKOFF_BASE_S * 2 ** (job_try - 1)
            log.warning(
                "email_send_retry",
                to=to,
                template=template,
                try_=job_try,
                defer_s=defer,
                error=str(exc),
            )
            raise Retry(defer=defer) from exc
        log.error("email_send_failed", to=to, template=template, tries=job_try, error=str(exc))
        return "failed"
    except Exception as exc:  # noqa: BLE001 — bad template/context: retries can't fix it
        log.error("email_render_failed", to=to, template=template, error=str(exc))
        return "failed"
    log.info("email_sent", to=to, template=template, message_id=message_id)
    return "sent"


async def send_invite_email(ctx: dict, invite_id: str) -> None:
    """Deliver the candidate_invite email for one requisition_invites row and
    stamp the outcome on it. Skips (without failing) rows that were revoked or
    whose requisition vanished/closed between enqueue and run."""
    from app.db.models import InviteLink, Organization, Requisition, RequisitionInvite
    from app.db.session import SessionLocal
    from app.domain.invites import candidate_invite_context

    async with SessionLocal() as db:
        invite = await db.get(RequisitionInvite, invite_id)
        if invite is None or invite.revoked_at is not None:
            return
        req = await db.get(Requisition, invite.requisition_id)
        if req is None or req.deleted_at is not None or req.status != "open":
            log.info("invite_email_skipped", invite_id=invite_id, reason="requisition_not_open")
            return
        org = await db.get(Organization, req.org_id)
        link = (
            (
                await db.execute(
                    select(InviteLink)
                    .where(
                        InviteLink.requisition_id == req.id,
                        InviteLink.kind == "open",
                        InviteLink.revoked_at.is_(None),
                    )
                    .order_by(InviteLink.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if link is None:
            log.error("invite_email_no_open_link", invite_id=invite_id, requisition_id=str(req.id))
            return
        to = invite.email
        context = candidate_invite_context(
            org_name=org.name if org else "Kandidly",
            interview_name=req.title,
            interview_url=f"{settings.base_url_web}/i/{link.token}",
            first_name=invite.first_name,
            closes_at=req.closes_at,
        )

    # Outside the session: delivery can Retry-loop for minutes. arq re-runs
    # this task (not bare send_email), so the row stays 'queued' until a
    # terminal outcome lands below.
    outcome = await send_email(ctx, to, "candidate_invite", context)

    async with SessionLocal() as db:
        invite = await db.get(RequisitionInvite, invite_id)
        if invite is None:
            return
        invite.email_status = outcome
        invite.last_emailed_at = datetime.now(UTC)
        await db.commit()


async def enqueue_email(to: str, template: str, context: dict) -> None:
    """Fire-and-forget enqueue for API code."""
    await enqueue("send_email", to, template, context)
