"""Candidate API (SPEC §12.2). Ownership is enforced on every route (SPEC §16.3).
Realtime/proctoring ingest routes (snapshots, proctor-events) are scaffolded in
api/candidate_proctor.py under Phase 4."""

from __future__ import annotations

from datetime import UTC
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
    StoredFile,
    User,
)
from app.domain import applications as apps
from app.domain.forms import validate_submission
from app.domain.links import resolve
from app.schemas.api import (
    ApplicationOut,
    ClaimOut,
    ConsentIn,
    FormPatchIn,
    FormSubmitOut,
    JoinOut,
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
        raise AppError("forbidden", "This invite is for a different email")

    # Idempotent re-entry: return the existing live application if any.
    existing = await apps.find_live_application(db, requisition.id, user.user_id)
    if existing is not None:
        return ClaimOut(application_id=existing.id, state=existing.state)

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
    app = await apps.get_owned(db, application_id, user.user_id)
    submission = (
        await db.execute(select(FormSubmission).where(FormSubmission.application_id == app.id))
    ).scalar_one_or_none()
    template = await db.get(FormTemplate, submission.template_id) if submission else None
    return ApplicationOut(
        id=app.id,
        requisition_id=app.requisition_id,
        state=app.state,
        state_timestamps=app.state_timestamps,
        interview_id=app.interview_id,
        template_schema=template.schema if template else None,
        answers=submission.answers if submission else None,
        resume_parse_status=submission.resume_parse_status if submission else None,
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
    app = await apps.get_owned(db, application_id, user.user_id)
    data = await image.read()
    file_id = new_id()
    key = storage.selfie_key(app.id)
    await storage.put_object(storage.BUCKET_SELFIES, key, data, "image/webp")
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


@router.post("/interviews/{interview_id}/snapshots", dependencies=[rate_limit("snapshots", 30)])
async def upload_snapshot(
    interview_id: UUID,
    image: UploadFile = File(...),
    captured_at: str = Form(...),
    faces_detected: int = Form(default=0),
    face_present: bool = Form(default=False),
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import datetime as dt

    from app.db.models import ProctoringSnapshot
    from app.domain import proctoring

    interview, app = await _owned_interview(db, interview_id, user)
    if interview.status not in ("live", "paused", "wrap_up"):
        raise AppError("conflict", "Interview is not accepting snapshots")
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
    await proctoring.require_consent(db, app.id)
    accepted = await proctoring.ingest_events(
        db,
        interview_id=interview_id,
        application_id=app.id,
        events=body.get("events") or [],
    )
    return {"accepted": accepted}


# --- join (SPEC §8.2, §12.2 #10) -------------------------------------------
@router.post("/applications/{application_id}/join")
async def join(
    application_id: UUID,
    user: AuthUser = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import JSONResponse

    from app.domain.interviews import mint_candidate_token, preflight_join

    app = await apps.get_owned(db, application_id, user.user_id)
    ready, reason = await preflight_join(db, app)
    if not ready:
        # 202 with a machine code (not_ready / queued) — SPEC §12.2 #10.
        return JSONResponse(status_code=202, content=reason)

    interview = await db.get(Interview, app.interview_id)
    token = mint_candidate_token(interview.room_name, app.id)  # type: ignore
    return JoinOut(livekit_url=settings.livekit_url, token=token, room_name=interview.room_name)  # type: ignore
