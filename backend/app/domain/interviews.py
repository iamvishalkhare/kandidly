"""Interview lifecycle helpers: join preflight and LiveKit token minting
(SPEC §8.2, §9.6, §12.2 #10)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    Application,
    Consent,
    Interview,
    QuestionPlan,
    StoredFile,
)
from app.domain import applications as apps
from app.domain.states import assert_interview_transition


async def _plan_ready(db: AsyncSession, interview_id: UUID) -> bool:
    plan = (
        await db.execute(select(QuestionPlan).where(QuestionPlan.interview_id == interview_id))
    ).scalar_one_or_none()
    return plan is not None and plan.status in ("ready", "fallback_generic")


async def preflight_join(db: AsyncSession, app: Application) -> tuple[bool, dict | None]:
    """Gate the candidate join (SPEC §12.2 #10). On success, advance app →
    in_interview and interview → lobby. On 'not ready' return a 202 body."""
    if app.interview_id is None:
        raise AppError("not_ready", "Interview not created")

    # Rejoin path: already in interview → just re-issue a token.
    if app.state == "in_interview":
        return True, None

    if not await _plan_ready(db, app.interview_id):
        return False, {"code": "not_ready", "retry_after_s": 3}

    consent = (
        await db.execute(select(Consent).where(Consent.application_id == app.id))
    ).scalar_one_or_none()
    if consent is None:
        raise AppError("not_ready", "Consent required before joining")

    selfie = (
        await db.execute(
            select(StoredFile).where(
                StoredFile.bucket == "kandidly-selfies",
                StoredFile.key == f"{app.id}/reference.webp",
            )
        )
    ).scalar_one_or_none()
    if selfie is None:
        raise AppError("not_ready", "Verification photo required before joining")

    # TODO(spec-gap): agent-pool saturation → 202 {"code":"queued","position":n}.
    # Requires live-count from Redis (SPEC §9.1); returns available in v1 skeleton.

    interview = await db.get(Interview, app.interview_id)
    if interview.status == "created":  # type: ignore
        assert_interview_transition(interview.status, "lobby")  # type: ignore
        interview.status = "lobby"  # type: ignore

    await apps.transition(db, app.id, "in_interview", "candidate")
    return True, None


def mint_candidate_token(room_name: str, application_id: UUID) -> str:
    """Mint a room-scoped LiveKit token for the candidate (SPEC §9.6).

    [VERIFY-DOC] LiveKit AccessToken/VideoGrants API. Identity is
    `cand-{application_id}`; grants: join room, publish mic+camera, subscribe,
    data. 2h TTL (SPEC §16.6)."""
    try:
        from livekit import api  # type: ignore

        token = (
            api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
            .with_identity(f"cand-{application_id}")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .with_ttl(_timedelta_hours(2))
        )
        return token.to_jwt()
    except Exception as exc:  # pragma: no cover - SDK/keys absent in dev
        raise AppError(
            "internal_error",
            "LiveKit token minting unavailable (configure LIVEKIT_* + install SDK)",
            detail={"error": str(exc)},
        ) from exc


def _timedelta_hours(h: int):
    from datetime import timedelta

    return timedelta(hours=h)


def mint_observer_token(room_name: str, user_id: UUID) -> str:
    """Hidden observer token (SPEC §9.6): subscribe-only, publish nothing,
    hidden=true so the candidate never renders them. [VERIFY-DOC hidden grant]."""
    try:
        from livekit import api  # type: ignore

        token = (
            api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
            .with_identity(f"obs-{user_id}")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=False,
                    can_subscribe=True,
                    can_publish_data=False,
                    hidden=True,
                )
            )
            .with_ttl(_timedelta_hours(2))
        )
        return token.to_jwt()
    except Exception as exc:  # pragma: no cover
        raise AppError(
            "internal_error",
            "LiveKit token minting unavailable",
            detail={"error": str(exc)},
        ) from exc
