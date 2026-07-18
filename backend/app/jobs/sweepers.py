"""Cron sweepers (SPEC §14, §16.4). All idempotent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select

from app.core.config import settings
from app.core.queue import enqueue
from app.db.models import (
    Application,
    Interview,
    ProctoringSnapshot,
    Requisition,
    StoredFile,
    Turn,
)
from app.db.session import SessionLocal
from app.domain import applications as apps

log = structlog.get_logger(__name__)

_STALE_LIVE_SECONDS = 90  # SPEC §14 sweep_abandoned
# Grace before a lobby/created interview whose agent never dispatched/connected
# gets force-ended — otherwise it has no turns to go stale on and, since it
# never reaches "live", the console ledger's `ended_at IS NOT NULL` filter
# hides it forever (2026-07-19 incident: candidate joined, LiveKit never
# dispatched the agent into the room, interview sat in "lobby" indefinitely).
_STALE_PRELIVE_SECONDS = 120


async def sweep_abandoned(ctx: dict) -> None:
    """Paused interviews past rejoin grace → ended(abandoned); live/wrap_up with
    stale activity > 90s → same; created/lobby stuck > 120s (agent never
    connected) → same. Uses last-turn time (or, pre-live, created_at) as the
    heartbeat proxy.

    TODO(Phase-2): prefer the Redis live:{interview_id} heartbeat key (SPEC §9.4)
    over last-turn time for precision."""
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        actives = (
            (
                await db.execute(
                    select(Interview).where(
                        Interview.status.in_(("created", "lobby", "live", "paused", "wrap_up"))
                    )
                )
            )
            .scalars()
            .all()
        )

        for interview in actives:
            last = (
                await db.execute(
                    select(func.max(func.coalesce(Turn.ended_at, Turn.started_at))).where(
                        Turn.interview_id == interview.id
                    )
                )
            ).scalar_one()
            reference = last or interview.started_at or interview.created_at
            idle = (now - reference).total_seconds()

            req = await db.get(Requisition, interview.requisition_id)
            grace = (req.interview_config or {}).get(  # type: ignore
                "rejoin_grace_seconds", settings.rejoin_grace_seconds
            )
            expired = (
                (interview.status == "paused" and idle > grace)
                or (interview.status in ("live", "wrap_up") and idle > _STALE_LIVE_SECONDS)
                or (interview.status in ("created", "lobby") and idle > _STALE_PRELIVE_SECONDS)
            )
            if not expired:
                continue

            interview.status = "ended"
            interview.ended_at = now
            interview.end_reason = "abandoned"
            app = await db.get(Application, interview.application_id)
            if app and app.state == "in_interview":
                await apps.transition(
                    db, app.id, "abandoned", "system", {"reason": "grace_expired"}
                )
            await db.commit()
            await enqueue("finalize_interview", str(interview.id))
            log.info("interview_swept_abandoned", interview_id=str(interview.id), idle_s=idle)


async def sweep_links_and_apps(ctx: dict) -> None:
    """Daily: applications stuck pre-interview whose requisition closed / passed
    closes_at → expired (SPEC §14, E3)."""
    now = datetime.now(UTC)
    pre = ("registered", "form_in_progress", "form_submitted", "plan_ready", "in_lobby")
    async with SessionLocal() as db:
        stuck = (
            (
                await db.execute(
                    select(Application)
                    .join(Requisition, Requisition.id == Application.requisition_id)
                    .where(
                        Application.state.in_(pre),
                        (Requisition.status == "closed")
                        | ((Requisition.closes_at.is_not(None)) & (Requisition.closes_at <= now)),
                    )
                )
            )
            .scalars()
            .all()
        )
        for app in stuck:
            await apps.transition(db, app.id, "expired", "system", {"reason": "requisition_closed"})
        await db.commit()
        if stuck:
            log.info("apps_expired", count=len(stuck))


async def retention_sweeper(ctx: dict) -> None:
    """Daily: delete snapshots + selfies RETENTION_DAYS_SNAPSHOTS after interview
    end (identity verdict retained); audio after RETENTION_DAYS_AUDIO (SPEC §16.4)."""
    from app.core import storage

    now = datetime.now(UTC)
    snap_cutoff = now - timedelta(days=settings.retention_days_snapshots)
    async with SessionLocal() as db:
        ended = (
            (
                await db.execute(
                    select(Interview).where(
                        Interview.ended_at.is_not(None), Interview.ended_at <= snap_cutoff
                    )
                )
            )
            .scalars()
            .all()
        )
        for interview in ended:
            snaps = (
                await db.execute(
                    select(ProctoringSnapshot, StoredFile)
                    .join(StoredFile, StoredFile.id == ProctoringSnapshot.file_id)
                    .where(ProctoringSnapshot.interview_id == interview.id)
                )
            ).all()
            for _snap, sf in snaps:
                try:
                    await storage.delete_object(sf.bucket, sf.key)
                except Exception as exc:  # noqa: BLE001
                    log.warning("retention_delete_failed", key=sf.key, error=str(exc))
        await db.commit()
    # TODO(Phase-5): audio recordings after RETENTION_DAYS_AUDIO; DPDP erasure cascade.
