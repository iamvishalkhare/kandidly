"""Proctoring vision pipeline: per-frame analysis + final integrity verdict.

analyze_snapshots — vision-LLM pass over proctoring snapshots. Enqueued
unconditionally by finalize_interview; self-gates (no-op when there are no
unanalyzed frames or no vision provider key, so frames simply stay "pending"
on the review page). EVERY captured frame is analyzed in capture order — no
sampling — up to a per-interview budget of settings.vision_max_frames (cost
ceiling; 180 = a 30-min interview at the 10s capture cadence), sent
settings.vision_batch_size images per LLM call.

Results land on each ProctoringSnapshot row: analyzed=True, signal (clamped
to the column's CHECK enum), faces_detected/face_present when the client sent
none, and client_meta.vision = {note, confidence, model, prompt_version}.

review_integrity — text-LLM verdict over all per-frame analyses + proctoring
events, chained by analyze_snapshots once the frame pass finishes. Writes
interviews.integrity_score (0-100) and interviews.integrity_review
{summary, band, model, prompt_version, frames_reviewed, generated_at}.
No report or event writes — the console reads these at request time
(api/console.py), so there is no ordering race with the scoring chain.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select

from app.core import storage
from app.core.config import settings
from app.core.errors import AppError
from app.core.queue import enqueue
from app.db.models import Interview, ProctoringEvent, ProctoringSnapshot, StoredFile
from app.db.session import SessionLocal
from app.domain.integrity import integrity_band
from app.llm.clients import ensure_provider_env, integrity_reviewer, proctor_vision
from app.llm.prompts import version_tag
from app.llm.schemas import FrameAnalysisOut, IntegrityReviewOut

log = structlog.get_logger(__name__)

_VALID_SIGNALS = {"clear", "attention_shift", "low_light", "no_face", "multiple_faces"}


async def analyze_snapshots(ctx: dict, interview_id: str) -> None:
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None:
            return
        started_at = interview.started_at
        already_analyzed = (
            await db.execute(
                select(func.count())
                .select_from(ProctoringSnapshot)
                .where(
                    ProctoringSnapshot.interview_id == interview.id,
                    ProctoringSnapshot.analyzed.is_(True),
                )
            )
        ).scalar_one()
        budget = max(0, settings.vision_max_frames - already_analyzed)
        rows = (
            (
                await db.execute(
                    select(ProctoringSnapshot, StoredFile.key)
                    .join(StoredFile, StoredFile.id == ProctoringSnapshot.file_id)
                    .where(
                        ProctoringSnapshot.interview_id == interview.id,
                        ProctoringSnapshot.analyzed.is_(False),
                    )
                    .order_by(ProctoringSnapshot.captured_at)
                    .limit(budget)
                )
            ).all()
            if budget
            else []
        )

    analyzed_count = 0
    if rows:
        try:
            ensure_provider_env(settings.vision_llm)
        except AppError:
            log.info("analyze_snapshots_no_provider", interview_id=interview_id)
            return
        analyzed_count = await _analyze_frames(interview_id, started_at, rows)

    log.info(
        "analyze_snapshots_done",
        interview_id=interview_id,
        pending=len(rows),
        analyzed=analyzed_count,
        budget=budget,
    )
    # Chain the final verdict pass (self-gating, idempotent) so it reruns
    # whenever the frame set it summarizes may have changed.
    await enqueue("review_integrity", interview_id)


async def _analyze_frames(
    interview_id: str, started_at: datetime | None, rows: list
) -> int:
    from pydantic_ai import BinaryContent  # lazy, like app.llm.clients

    agent = proctor_vision()
    analyzed_count = 0

    for start in range(0, len(rows), settings.vision_batch_size):
        batch = rows[start : start + settings.vision_batch_size]

        lines = []
        images: list = []
        try:
            for i, (snap, key) in enumerate(batch):
                offset = (
                    int((snap.captured_at - started_at).total_seconds()) if started_at else 0
                )
                lines.append(f"Frame {i}: captured {offset}s into the interview")
                data = await storage.get_object(storage.BUCKET_SNAPSHOTS, key)
                images.append(BinaryContent(data=data, media_type="image/webp"))
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "analyze_snapshots_download_failed", interview_id=interview_id, error=str(exc)
            )
            continue
        prompt = "Analyze these webcam frames, in order:\n" + "\n".join(lines)

        frames: list[FrameAnalysisOut] | None = None
        for attempt in range(2):  # one retry per batch
            try:
                result = await agent.run([prompt, *images])
                out = getattr(result, "output", None) or getattr(result, "data", None)
                frames = out.frames  # type: ignore[union-attr]
                break
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "analyze_snapshots_llm_failed",
                    interview_id=interview_id,
                    attempt=attempt,
                    error=str(exc)[:200],
                )
        if frames is None:
            continue  # rows stay analyzed=False; a re-run picks them up

        by_index = {f.index: f for f in frames}
        async with SessionLocal() as db:
            for i, (snap, _key) in enumerate(batch):
                verdict = by_index.get(i)
                if verdict is None:
                    continue
                row = await db.get(ProctoringSnapshot, snap.id)
                if row is None or row.analyzed:
                    continue
                row.analyzed = True
                row.signal = verdict.signal if verdict.signal in _VALID_SIGNALS else "clear"
                if row.faces_detected is None:
                    row.faces_detected = verdict.faces_detected
                if row.face_present is None:
                    row.face_present = verdict.faces_detected > 0
                row.client_meta = {
                    **(row.client_meta or {}),
                    "vision": {
                        "note": verdict.note,
                        "confidence": verdict.confidence,
                        "model": settings.vision_llm,
                        "prompt_version": version_tag("proctor_vision"),
                    },
                }
                analyzed_count += 1
            await db.commit()

    return analyzed_count


async def review_integrity(ctx: dict, interview_id: str) -> None:
    """Final integrity verdict from the per-frame analyses (LLM, idempotent)."""
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None:
            return
        started_at = interview.started_at
        snaps = (
            (
                await db.execute(
                    select(ProctoringSnapshot)
                    .where(
                        ProctoringSnapshot.interview_id == interview.id,
                        ProctoringSnapshot.analyzed.is_(True),
                    )
                    .order_by(ProctoringSnapshot.captured_at)
                )
            )
            .scalars()
            .all()
        )
        events = (
            await db.execute(
                select(ProctoringEvent.type, ProctoringEvent.severity, func.count())
                .where(ProctoringEvent.interview_id == interview.id)
                .group_by(ProctoringEvent.type, ProctoringEvent.severity)
            )
        ).all()
        duration_s = interview.elapsed_active_seconds or 0

    if not snaps:
        return
    try:
        ensure_provider_env(settings.integrity_llm)
    except AppError:
        log.info("review_integrity_no_provider", interview_id=interview_id)
        return

    frame_lines = []
    for snap in snaps:
        offset = int((snap.captured_at - started_at).total_seconds()) if started_at else 0
        vision = (snap.client_meta or {}).get("vision") or {}
        confidence = vision.get("confidence")
        frame_lines.append(
            f"- t={offset}s signal={snap.signal or 'clear'}"
            f" faces={snap.faces_detected if snap.faces_detected is not None else '?'}"
            + (f" confidence={confidence}" if confidence is not None else "")
            + (f" note={vision.get('note')}" if vision.get("note") else "")
        )
    event_lines = [
        f"- {ev_type} (severity {severity}) × {count}" for ev_type, severity, count in events
    ]
    prompt = (
        f"Interview duration: about {max(1, round(duration_s / 60))} minutes.\n\n"
        f"Frame-by-frame observations ({len(snaps)} frames, in order):\n"
        + "\n".join(frame_lines)
        + "\n\nBrowser proctoring events:\n"
        + ("\n".join(event_lines) if event_lines else "- none")
    )

    agent = integrity_reviewer()
    out: IntegrityReviewOut | None = None
    for attempt in range(2):  # one retry, mirroring the frame batches
        try:
            result = await agent.run(prompt)
            out = getattr(result, "output", None) or getattr(result, "data", None)
            break
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "review_integrity_llm_failed",
                interview_id=interview_id,
                attempt=attempt,
                error=str(exc)[:200],
            )
    if out is None:
        return  # score stays NULL; the console keeps showing "analyzing"

    score = max(0, min(100, out.score))
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None:
            return
        interview.integrity_score = score
        interview.integrity_review = {
            "summary": out.summary,
            "band": integrity_band(score),
            "model": settings.integrity_llm,
            "prompt_version": version_tag("integrity"),
            "frames_reviewed": len(snaps),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        await db.commit()

    log.info(
        "review_integrity_done",
        interview_id=interview_id,
        score=score,
        band=integrity_band(score),
        frames=len(snaps),
    )
