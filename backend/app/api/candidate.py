"""Candidate API (SPEC §12.2). Ownership is enforced on every route (SPEC §16.3).
Realtime/proctoring ingest routes (snapshots, proctor-events) are scaffolded in
api/candidate_proctor.py under Phase 4."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.captcha import require_captcha
from app.core.config import settings
from app.core.deps import get_db, require_candidate
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.queue import enqueue
from app.core.ratelimit import rate_limit
from app.core.security import AuthUser
from app.db.models import (
    Consent,
    FormSubmission,
    FormTemplate,
    Interview,
    InviteLink,
    Requisition,
    RequisitionInvite,
    StoredFile,
    User,
)
from app.domain import applications as apps
from app.domain.forms import validate_submission
from app.domain.links import resolve
from app.domain.plan import ensure_interview_capacity
from app.schemas.api import (
    ApplicationOut,
    ClaimOut,
    ConsentIn,
    FormPatchIn,
    FormSubmitOut,
    JoinOut,
    ProctoringJoinOut,
    RecordingCompleteIn,
)

router = APIRouter(prefix="/api/candidate", tags=["candidate"])

_RESUME_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}
_MAX_RESUME_BYTES = 10 * 1024 * 1024


# --- claim (SPEC §8.5, §12.2 #3) -------------------------------------------
@router.post("/i/{token}/claim", response_model=ClaimOut, dependencies=[rate_limit("claim", 10)])
async def claim(
    token: str,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ClaimOut:
    # Lock the link row for atomic validate + increment (SPEC §8.5).
    link = (
        await db.execute(select(InviteLink).where(InviteLink.token == token).with_for_update())
    ).scalar_one_or_none()
    requisition = await db.get(Requisition, link.requisition_id) if link else None
    res = resolve(link, requisition)
    if not res.status_ok or link is None or requisition is None:
        raise AppError("link_invalid", "Invite link is not usable", detail={"reason": res.reason})

    if link.kind == "personal" and (link.email or "").lower() != user.email.lower():
        # detail.reason lets the SPA distinguish "signed in with the wrong
        # email" (offer account switch) from a role-based 403.
        raise AppError(
            "forbidden",
            "This invite is for a different email",
            detail={"reason": "email_mismatch"},
        )

    # Free-plan hold: once the org's cumulative interview count hits the
    # threshold, every new attempt is refused with ER0402 (402).
    await ensure_interview_capacity(db, requisition.org_id)

    # Idempotent re-entry: return the existing live application if any.
    # Deliberately checked BEFORE the invite-only gate so a later uninvite
    # never kicks a candidate who is already mid-flight.
    existing = await apps.find_live_application(db, requisition.id, user.user_id)
    if existing is not None:
        return ClaimOut(application_id=existing.id, state=existing.state)

    # Invite-only requisitions: the open link is a guest-list door, not a
    # bypass — the authed email must be on requisition_invites. Personal
    # links already carry their own (stricter) email match above.
    from app.schemas.interview_config import InterviewConfig

    if InterviewConfig(**(requisition.interview_config or {})).invite_only and link.kind == "open":
        invited = (
            await db.execute(
                select(RequisitionInvite.id).where(
                    RequisitionInvite.requisition_id == requisition.id,
                    RequisitionInvite.email == user.email.strip().lower(),
                    RequisitionInvite.revoked_at.is_(None),
                )
            )
        ).first()
        if invited is None:
            # detail.reason lets the SPA show "sign in with the invited
            # email" + account switch, distinct from other 403s.
            raise AppError(
                "forbidden",
                "This interview is invite-only",
                detail={"reason": "not_invited"},
            )

    app = await apps.create_application(
        db,
        requisition_id=requisition.id,
        candidate_id=user.user_id,
        invite_link_id=link.id,
        template_id=requisition.form_template_id,
    )
    link.use_count += 1
    return ClaimOut(application_id=app.id, state=app.state)


# --- read (SPEC §12.2 #4) ---------------------------------------------------
@router.get("/applications/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: UUID,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> ApplicationOut:
    from app.domain import proctoring
    from app.schemas.interview_config import InterviewConfig

    app = await apps.get_owned(db, application_id, user.user_id)
    submission = (
        await db.execute(select(FormSubmission).where(FormSubmission.application_id == app.id))
    ).scalar_one_or_none()
    template = await db.get(FormTemplate, submission.template_id) if submission else None
    requisition = await db.get(Requisition, app.requisition_id)
    config = InterviewConfig(**((requisition.interview_config if requisition else None) or {}))
    return ApplicationOut(
        id=app.id,
        requisition_id=app.requisition_id,
        state=app.state,
        state_timestamps=app.state_timestamps,
        interview_id=app.interview_id,
        template_schema=template.schema if template else None,
        answers=submission.answers if submission else None,
        resume_parse_status=submission.resume_parse_status if submission else None,
        proctoring_enabled=proctoring.config_for(
            requisition.interview_config if requisition else None
        ).enabled,
        duration_minutes=config.max_duration_seconds // 60,
    )


# --- autosave (SPEC §8.1.4, §12.2 #5) --------------------------------------
@router.patch("/applications/{application_id}/form", dependencies=[rate_limit("autosave", 60)])
async def patch_form(
    application_id: UUID,
    body: FormPatchIn,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    app = await apps.get_owned(db, application_id, user.user_id)
    if app.state in (
        "form_submitted",
        "plan_ready",
        "in_lobby",
        "in_interview",
        "completed",
        "scored",
        "reviewed",
    ):
        raise AppError("conflict", "Form already submitted")

    submission = (
        await db.execute(select(FormSubmission).where(FormSubmission.application_id == app.id))
    ).scalar_one()
    # Shallow merge (SPEC §8.1.4).
    merged = dict(submission.answers or {})
    merged.update(body.answers_partial)
    submission.answers = merged

    if app.state == "registered":
        await apps.transition(db, app.id, "form_in_progress", "candidate")
    return {"ok": True}


# --- resume upload (SPEC §8.6.1, §12.2 #6) ---------------------------------
@router.post("/applications/{application_id}/resume")
async def upload_resume(
    application_id: UUID,
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    app = await apps.get_owned(db, application_id, user.user_id)
    ext = _RESUME_MIME.get(file.content_type or "")
    if ext is None:
        raise AppError("validation_error", "Resume must be PDF or DOCX")
    data = await file.read()
    if len(data) > _MAX_RESUME_BYTES:
        raise AppError("validation_error", "Resume exceeds 10 MB")

    submission = (
        await db.execute(select(FormSubmission).where(FormSubmission.application_id == app.id))
    ).scalar_one()

    file_id = new_id()
    key = storage.resume_key(app.id, file_id, ext)
    await storage.put_object(storage.BUCKET_RESUMES, key, data, file.content_type)  # type: ignore
    db.add(
        StoredFile(
            id=file_id,
            bucket=storage.BUCKET_RESUMES,
            key=key,
            mime=file.content_type,
            bytes=len(data),
            created_by=user.user_id,
        )
    )
    # Flush the file row before referencing it: models use raw FK columns (no
    # relationship()), so the unit of work can't infer inter-mapper ordering.
    await db.flush()
    submission.resume_file_id = file_id
    submission.resume_parse_status = "pending"
    await db.flush()
    # Parse immediately — do NOT wait for form submit (SPEC §8.6.1).
    await enqueue("parse_resume", str(submission.id))
    return {"file_id": str(file_id), "parse_status": "pending"}


# --- submit (SPEC §8.2, §12.2 #7) ------------------------------------------
# reCAPTCHA v3 guards this endpoint: it creates the Interview and enqueues the
# plan-generation LLM job, so it's the costly step worth gating against bots.
@router.post(
    "/applications/{application_id}/form/submit",
    response_model=FormSubmitOut,
    dependencies=[require_captcha("form_submit")],
)
async def submit_form(
    application_id: UUID,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> FormSubmitOut:
    from datetime import datetime

    app = await apps.get_owned(db, application_id, user.user_id)
    submission = (
        await db.execute(select(FormSubmission).where(FormSubmission.application_id == app.id))
    ).scalar_one()
    template = await db.get(FormTemplate, submission.template_id)
    validate_submission(template.schema, submission.answers or {})  # type: ignore

    submission.submitted_at = datetime.now(UTC)

    # Surface the candidate's name for admin views once the form is in.
    full_name = (submission.answers or {}).get("full_name")
    if full_name and isinstance(full_name, str):
        candidate = await db.get(User, user.user_id)
        if candidate is not None and candidate.display_name is None:
            candidate.display_name = full_name.strip()

    # Free-plan hold re-check at the point the Interview row is actually
    # created — a claim that slipped in under the threshold must not push the
    # org past it later.
    requisition = await db.get(Requisition, app.requisition_id)
    if requisition is not None:
        await ensure_interview_capacity(db, requisition.org_id)

    # Create the interview row (status 'created', room name) — SPEC §8.2.
    seq = (await db.execute(sa_text("SELECT nextval('interview_code_seq')"))).scalar_one()
    interview = Interview(
        id=new_id(),
        application_id=app.id,
        requisition_id=app.requisition_id,
        code=f"INT-{seq}",
        status="created",
    )
    interview.room_name = f"kndl-{interview.id}"
    db.add(interview)
    await db.flush()
    app.interview_id = interview.id

    await apps.transition(db, app.id, "form_submitted", "candidate")
    await enqueue("generate_plan", str(interview.id))
    # Scrape the candidate's GitHub / site / blog links; generate_plan waits for
    # this and folds the digest into the seed questions (SPEC §8.6).
    await enqueue("enrich_sources", str(interview.id))

    # Cache a PARTIAL context bundle (form + requisition) in Redis now, so it's
    # there the instant the candidate submits; the background pipeline fills in
    # resume/scraped/plan and flips it to "ready" (interview_context.py).
    from app.domain.interview_context import assemble_context, cache_context

    req = await db.get(Requisition, app.requisition_id)
    partial = assemble_context(
        req=req,
        submission=submission,
        field_hints=(template.field_hints if template else {}),  # type: ignore
        plan_nodes=None,
        status="partial",
    )
    await cache_context(interview.id, partial)
    return FormSubmitOut(interview_id=interview.id)


# --- consent (SPEC §10.1, §12.2 #8) ----------------------------------------
@router.post("/applications/{application_id}/consent")
async def post_consent(
    application_id: UUID,
    body: ConsentIn,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    app = await apps.get_owned(db, application_id, user.user_id)
    if not (body.recording_ack and body.monitoring_ack):
        raise AppError("validation_error", "Both consents are required to proceed")
    existing = (
        await db.execute(select(Consent).where(Consent.application_id == app.id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            Consent(
                id=new_id(),
                application_id=app.id,
                user_id=user.user_id,
                consent_version=body.consent_version,
                recording_ack=True,
                monitoring_ack=True,
            )
        )
    if app.state in ("form_submitted", "plan_ready"):
        await apps.transition(db, app.id, "in_lobby", "candidate")
    return {"ok": True}


# --- selfie (SPEC §10.1, §12.2 #9) -----------------------------------------
@router.post("/applications/{application_id}/selfie")
async def post_selfie(
    application_id: UUID,
    image: UploadFile = File(...),
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # No proctoring gate: the verification selfie is always required (it
    # identifies the candidate on the review page); the proctoring toggle only
    # controls the periodic snapshot loop during the interview.
    app = await apps.get_owned(db, application_id, user.user_id)
    data = await image.read()
    key = storage.selfie_key(app.id)
    await storage.put_object(storage.BUCKET_SELFIES, key, data, "image/webp")
    # Retakes reuse the fixed key, and stored_files has a unique (bucket, key)
    # constraint — update the existing row instead of inserting a duplicate.
    existing = (
        await db.execute(
            select(StoredFile).where(
                StoredFile.bucket == storage.BUCKET_SELFIES, StoredFile.key == key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.bytes = len(data)
        existing.created_by = user.user_id
        return {"file_id": str(existing.id)}
    file_id = new_id()
    db.add(
        StoredFile(
            id=file_id,
            bucket=storage.BUCKET_SELFIES,
            key=key,
            mime="image/webp",
            bytes=len(data),
            created_by=user.user_id,
        )
    )
    return {"file_id": str(file_id)}


# --- proctoring ingest (SPEC §10.2–10.3, §12.2 #11–12) ----------------------
async def _owned_interview(db: AsyncSession, interview_id: UUID, user: AuthUser):
    from app.db.models import Interview as InterviewModel

    interview = await db.get(InterviewModel, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    app = await apps.get_owned(db, interview.application_id, user.user_id)
    return interview, app


async def _require_proctoring_enabled(db: AsyncSession, requisition_id: UUID) -> None:
    """Reject proctoring data (snapshots/events) when the requisition's
    proctoring toggle is off — the client shouldn't send any, but enforce it.
    The verification selfie is NOT gated: it is always required."""
    from app.domain import proctoring

    requisition = await db.get(Requisition, requisition_id)
    cfg = proctoring.config_for(requisition.interview_config if requisition else None)
    if not cfg.enabled:
        raise AppError("forbidden", "Proctoring is disabled for this interview")


@router.post("/interviews/{interview_id}/snapshots", dependencies=[rate_limit("snapshots", 30)])
async def upload_snapshot(
    interview_id: UUID,
    image: UploadFile = File(...),
    captured_at: str = Form(...),
    # None (not 0/False) when the browser does no local face detection —
    # derive_snapshot_events treats absent values as neutral, so a plain
    # capture loop doesn't falsely trip no_face_sustained.
    faces_detected: int | None = Form(default=None),
    face_present: bool | None = Form(default=None),
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import datetime as dt

    from app.db.models import ProctoringSnapshot
    from app.domain import proctoring

    interview, app = await _owned_interview(db, interview_id, user)
    if interview.status not in ("live", "paused", "wrap_up"):
        raise AppError("conflict", "Interview is not accepting snapshots")
    await _require_proctoring_enabled(db, app.requisition_id)
    await proctoring.require_consent(db, app.id)

    data = await image.read()
    file_id = new_id()
    epoch_ms = int(dt.fromisoformat(captured_at).timestamp() * 1000)
    key = storage.snapshot_key(interview_id, epoch_ms)
    await storage.put_object(storage.BUCKET_SNAPSHOTS, key, data, "image/webp")
    db.add(
        StoredFile(
            id=file_id,
            bucket=storage.BUCKET_SNAPSHOTS,
            key=key,
            mime="image/webp",
            bytes=len(data),
            created_by=user.user_id,
        )
    )
    await db.flush()
    snapshot = ProctoringSnapshot(
        id=new_id(),
        interview_id=interview_id,
        file_id=file_id,
        captured_at=dt.fromisoformat(captured_at),
        faces_detected=faces_detected,
        face_present=face_present,
    )
    db.add(snapshot)
    await db.flush()
    await proctoring.derive_snapshot_events(
        db, interview_id=interview_id, application_id=app.id, snapshot=snapshot
    )
    return {"ok": True}


@router.post(
    "/interviews/{interview_id}/proctor-events", dependencies=[rate_limit("proctor_events", 60)]
)
async def post_proctor_events(
    interview_id: UUID,
    body: dict,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Beacon fallback + regular batches (SPEC §10.2). Body: {events:[...]}."""
    from app.domain import proctoring

    interview, app = await _owned_interview(db, interview_id, user)
    await _require_proctoring_enabled(db, app.requisition_id)
    await proctoring.require_consent(db, app.id)
    accepted = await proctoring.ingest_events(
        db,
        interview_id=interview_id,
        application_id=app.id,
        events=body.get("events") or [],
    )
    return {"accepted": accepted}


# --- interview recording ingest (docs/ARTIFACTS.md) -------------------------
# The browser records mixed mic+agent audio with MediaRecorder and uploads
# ~15s chunks; on end it posts /recording/complete which enqueues the
# process_recording job (concat → transcode → waveform peaks).
_RECORDING_GRACE_S = 180  # accept trailing chunks shortly after the interview ends
_MAX_CHUNK_BYTES = 8 * 1024 * 1024
_CHUNK_MIME_EXT = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/mp4": "mp4",
    "audio/ogg": "ogg",
}


def _recording_window_open(interview: Interview) -> bool:
    # Status alone is not enough: the agent flips ended→finalized within
    # seconds while the browser's final chunk + complete call arrive after.
    if interview.status in ("live", "paused", "wrap_up"):
        return True
    if interview.ended_at is not None:
        return (datetime.now(UTC) - interview.ended_at).total_seconds() <= _RECORDING_GRACE_S
    return False


@router.post(
    "/interviews/{interview_id}/recording/chunks",
    dependencies=[rate_limit("recording_chunks", 60)],
)
async def upload_recording_chunk(
    interview_id: UUID,
    chunk: UploadFile = File(...),
    seq: int = Form(...),
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.domain import proctoring

    interview, app = await _owned_interview(db, interview_id, user)
    if not _recording_window_open(interview):
        raise AppError("conflict", "Interview is not accepting recording chunks")
    await proctoring.require_consent(db, app.id)

    data = await chunk.read()
    if len(data) > _MAX_CHUNK_BYTES:
        raise AppError("validation_error", "Recording chunk too large", status_code=413)
    content_type = (chunk.content_type or "").split(";", 1)[0].strip().lower()
    ext = _CHUNK_MIME_EXT.get(content_type, "bin")
    # Transient objects — no StoredFile rows; process_recording deletes them.
    await storage.put_object(
        storage.BUCKET_RECORDINGS,
        storage.recording_chunk_key(interview_id, seq, ext),
        data,
        content_type or "application/octet-stream",
    )
    return {"ok": True, "seq": seq}


@router.post("/interviews/{interview_id}/recording/complete")
async def complete_recording(
    interview_id: UUID,
    body: RecordingCompleteIn,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.domain import proctoring

    interview, app = await _owned_interview(db, interview_id, user)
    if interview.audio_recording_id is not None:
        return {"ok": True}  # already finalized — idempotent
    if not _recording_window_open(interview):
        raise AppError("conflict", "Interview is not accepting recording data")
    await proctoring.require_consent(db, app.id)

    manifest = {
        "chunks": body.chunks,
        "started_at": body.started_at.isoformat(),
        "mime": body.mime,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    await storage.put_object(
        storage.BUCKET_RECORDINGS,
        storage.recording_manifest_key(interview_id),
        json.dumps(manifest).encode(),
        "application/json",
    )
    await enqueue("process_recording", str(interview_id))
    return {"ok": True}


# --- join (SPEC §8.2, §12.2 #10) -------------------------------------------
@router.post("/applications/{application_id}/join")
async def join(
    application_id: UUID,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import JSONResponse

    from app.domain import proctoring
    from app.domain.interviews import mint_candidate_token, preflight_join

    app = await apps.get_owned(db, application_id, user.user_id)
    ready, reason = await preflight_join(db, app)
    if not ready:
        # 202 with a machine code (not_ready / queued) — SPEC §12.2 #10.
        return JSONResponse(status_code=202, content=reason)

    interview = await db.get(Interview, app.interview_id)
    requisition = await db.get(Requisition, app.requisition_id)
    cfg = proctoring.config_for(requisition.interview_config if requisition else None)
    token = mint_candidate_token(interview.room_name, app.id)  # type: ignore
    return JoinOut(
        livekit_url=settings.livekit_url,
        token=token,
        room_name=interview.room_name,  # type: ignore
        proctoring=ProctoringJoinOut(
            enabled=cfg.enabled, snapshot_interval_s=cfg.snapshot_interval_s
        ),
    )
