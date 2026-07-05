"""Proctoring domain (SPEC §10.2–§10.3): event type registry, severity mapping,
and snapshot-derived events. Presentation rule (§10.6): flags with evidence for
human judgment — never auto-reject or accuse."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Consent, ProctoringEvent, ProctoringSnapshot

# Closed set of browser event types (SPEC §10.2).
BROWSER_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "visibility_hidden",
        "visibility_visible",
        "window_blur",
        "window_focus",
        "fullscreen_exit",
        "paste_attempt",
        "copy_attempt",
        "right_click",
        "multi_display_detected",
        "camera_off",
        "mic_off",
        "page_unload",
    }
)

# System/audio/video_meta types used elsewhere in the spec.
SYSTEM_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "ctrl_parse_error",
        "stt_empty",
        "snapshot_gap",
        "conduct_flag",
        "second_voice_detected",
        "answer_latency_anomaly",
        "multiple_faces",
        "no_face_sustained",
    }
)

# Baseline severity per browser type (SPEC §10.2). Duration-sensitive upgrades
# (blur/hidden > 5s → medium) are applied in classify().
_BASE_SEVERITY: dict[str, str] = {
    "visibility_hidden": "low",
    "visibility_visible": "info",
    "window_blur": "low",
    "window_focus": "info",
    "fullscreen_exit": "low",
    "paste_attempt": "medium",
    "copy_attempt": "low",
    "right_click": "info",
    "multi_display_detected": "low",
    "camera_off": "high",
    "mic_off": "medium",
    "page_unload": "info",
}


def classify(event_type: str, payload: dict) -> str:
    """Severity for a browser event (constant table + duration upgrades)."""
    severity = _BASE_SEVERITY.get(event_type, "info")
    duration_s = payload.get("duration_s")
    if event_type in ("visibility_hidden", "window_blur") and (duration_s or 0) > 5:
        severity = "medium"
    return severity


async def require_consent(db: AsyncSession, application_id: UUID) -> None:
    """SPEC §16.1: no snapshot/recording/proctor event is accepted without a
    consents row. Enforced on every ingest route."""
    consent = (
        await db.execute(select(Consent).where(Consent.application_id == application_id))
    ).scalar_one_or_none()
    if consent is None:
        raise AppError("forbidden", "Consent required before monitoring data is accepted")


async def ingest_events(
    db: AsyncSession,
    *,
    interview_id: UUID,
    application_id: UUID,
    events: list[dict],
    default_source: str = "browser",
) -> int:
    """Insert a batch of proctor events (append-only). Unknown types are dropped
    (closed set, SPEC §10.2). Returns accepted count."""
    accepted = 0
    for e in events:
        etype = e.get("type")
        source = e.get("source", default_source)
        if source == "browser" and etype not in BROWSER_EVENT_TYPES:
            continue
        if source != "browser" and etype not in SYSTEM_EVENT_TYPES:
            continue
        payload = e.get("payload") or {}
        severity = e.get("severity") if source != "browser" else classify(etype, payload)  # type: ignore
        client_ts = e.get("client_ts")
        db.add(
            ProctoringEvent(
                interview_id=interview_id,
                application_id=application_id,
                source=source,
                type=etype,
                severity=severity or "info",
                payload=payload,
                client_ts=datetime.fromisoformat(client_ts) if client_ts else None,
            )
        )
        accepted += 1
    return accepted


async def derive_snapshot_events(
    db: AsyncSession,
    *,
    interview_id: UUID,
    application_id: UUID,
    snapshot: ProctoringSnapshot,
) -> None:
    """Synchronous derived events on snapshot insert (SPEC §10.3):
    - faces_detected ≥ 2 → multiple_faces (high)
    - last 4 snapshots all face_present=false → no_face_sustained (medium,
      deduped to max 1 per 60 s)."""
    if (snapshot.faces_detected or 0) >= 2:
        db.add(
            ProctoringEvent(
                interview_id=interview_id,
                application_id=application_id,
                source="video_meta",
                type="multiple_faces",
                severity="high",
                payload={
                    "faces_detected": snapshot.faces_detected,
                    "snapshot_id": str(snapshot.id),
                },
            )
        )

    recent = (
        (
            await db.execute(
                select(ProctoringSnapshot.face_present)
                .where(ProctoringSnapshot.interview_id == interview_id)
                .order_by(ProctoringSnapshot.captured_at.desc())
                .limit(4)
            )
        )
        .scalars()
        .all()
    )
    if len(recent) == 4 and all(fp is False for fp in recent):
        cutoff = datetime.now(UTC) - timedelta(seconds=60)
        dup = (
            await db.execute(
                select(ProctoringEvent.id)
                .where(
                    ProctoringEvent.interview_id == interview_id,
                    ProctoringEvent.type == "no_face_sustained",
                    ProctoringEvent.server_ts >= cutoff,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if dup is None:
            db.add(
                ProctoringEvent(
                    interview_id=interview_id,
                    application_id=application_id,
                    source="video_meta",
                    type="no_face_sustained",
                    severity="medium",
                    payload={"window": 4},
                )
            )
