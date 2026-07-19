"""Console API — serves the /console admin UI (dashboard, requisition grid +
builder, interviews ledger, interview review). Sits beside the SPEC §12.1
admin surface under /api/admin/console; same auth, audit on mutations.

Builder payload ↔ template/rubric mapping is pure logic in app.domain.builder.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy import delete as sa_delete
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import settings
from app.core.deps import get_db, require_role
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.queue import enqueue
from app.core.ratelimit import rate_limit
from app.core.security import AuthUser
from app.db.models import (
    Application,
    AuditLog,
    CatalogEntry,
    Evaluation,
    EvidenceNote,
    FormSubmission,
    FormTemplate,
    IdentityCheck,
    Injection,
    Interview,
    InviteLink,
    Organization,
    ProctoringEvent,
    ProctoringSnapshot,
    QuestionPlan,
    Report,
    Requisition,
    RequisitionInvite,
    Rubric,
    RubricCriterion,
    ScoringJob,
    StoredFile,
    Turn,
    User,
)
from app.domain import interview_context
from app.domain import invites as invites_domain
from app.domain.audit import record_audit
from app.domain.builder import (
    builder_fields_to_schema,
    builder_rubric_to_criteria,
    recommendation_for,
    schema_to_builder_fields,
)
from app.domain.forms import validate_template
from app.domain.integrity import integrity_band
from app.domain.links import generate_token
from app.domain.plan import (
    ensure_can_create_requisition,
    interview_count,
    requisition_count,
)
from app.domain.rubrics import validate_criteria
from app.schemas.interview_config import InterviewConfig, ProctoringConfig

router = APIRouter(prefix="/api/admin/console", tags=["console"])
_admin = Depends(require_role("admin", "recruiter"))
log = structlog.get_logger(__name__)

_COMPLETED_STATES = ("scored", "reviewed")


# --------------------------------------------------------------------------- #
# Schemas (console-shaped; the SPEC §12.1 surface keeps its own in schemas/api)
# --------------------------------------------------------------------------- #
class BuilderField(BaseModel):
    id: str = ""
    type: Literal[
        "text", "textarea", "multiple_choice", "multi_select", "range", "date", "file", "social"
    ]
    label: str
    placeholder: str = ""
    required: bool = False
    options: list[str] = []


class BuilderCriterion(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    weight: float


class BuilderQuestion(BaseModel):
    id: str = ""
    text: str


class ConsoleRequisitionIn(BaseModel):
    title: str
    domain: str
    objective: str = ""
    skills: list[str] = []
    tone: Literal["conversational", "friendly", "technical", "structured", "bar_raiser"] = (
        "conversational"
    )
    sample_questions: list[BuilderQuestion] = []
    screening_fields: list[BuilderField] = []
    rubric: list[BuilderCriterion] = []
    # ISO date (YYYY-MM-DD); the interview link goes offline at the end of
    # this day. Stored in interview_config.ends_at, mirrored to closes_at.
    end_date: str | None = None
    # Webcam snapshots every 10s during the interview (proctoring pipeline).
    proctoring_enabled: bool = True
    # Access policy: True → only emails on the requisition's guest list
    # (requisition_invites) can claim; the interview URL stays the same.
    invite_only: bool = False
    # Interview length in minutes; the agent paces and ends the interview to
    # fit this window (stored as interview_config.max_duration_seconds).
    duration_minutes: int = Field(default=30, ge=15, le=90)
    deploy: bool = True  # False → "Save as Offline" (draft)

    @field_validator("end_date")
    @classmethod
    def _end_date_iso(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        value = v.strip()
        try:
            if "T" in value or " " in value:
                datetime.fromisoformat(value.replace(" ", "T"))
            else:
                date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("end_date must be an ISO date (YYYY-MM-DD) or datetime") from exc
        return value


class ConsoleRequisitionOut(BaseModel):
    id: UUID
    code: str
    title: str
    domain: str | None = None
    technical_requirements: list[str] = []
    status: str
    live: bool
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    created_at: datetime
    invite_token: str | None = None
    invite_only: bool = False
    clicks: int = 0
    completed: int = 0


class ConsoleRequisitionDetailOut(ConsoleRequisitionOut):
    objective: str | None = None
    tone: str = "conversational"
    end_date: str | None = None
    proctoring_enabled: bool = True
    duration_minutes: int = 30
    sample_questions: list[BuilderQuestion] = []
    screening_fields: list[BuilderField] = []
    rubric: list[BuilderCriterion] = []


class CatalogOut(BaseModel):
    domains: list[str]
    skills: list[str]
    job_titles: list[str]


class ConsoleInterviewOut(BaseModel):
    id: UUID
    code: str | None = None
    candidate_name: str
    candidate_email: str | None = None
    requisition_code: str
    requisition_title: str
    domain: str | None = None
    scoring_status: Literal["evaluating", "done"]
    decision: str | None = None  # human review decision; null until reviewed
    concluded_at: datetime | None = None
    duration_seconds: int = 0
    final_score: float | None = None


class TranscriptTurnOut(BaseModel):
    id: UUID
    seconds: int
    speaker: str  # 'kandidly' | 'candidate'
    text: str


class RubricAssessmentOut(BaseModel):
    key: str
    label: str
    weight: float
    score: float
    summary: str
    reasoning: str


class ScreeningAnswerOut(BaseModel):
    key: str
    label: str
    field_type: str
    required: bool = False
    answered: bool = False
    answer: str | None = None
    file_url: str | None = None
    file_mime: str | None = None
    file_name: str | None = None


class ProctorFrameOut(BaseModel):
    id: UUID
    seconds: int
    signal: str | None = None
    image_url: str | None = None
    analyzed: bool = False
    note: str | None = None  # vision job's observation (client_meta.vision.note)


class ProctorFramePageOut(BaseModel):
    """One filmstrip page, ordered by capture time (infinite scroll)."""

    items: list[ProctorFrameOut]
    total: int
    offset: int
    limit: int


class IntegrityOut(BaseModel):
    """Read-time aggregation over snapshots + proctor events. The verdict is
    the LLM integrity review (score 0-100, banded) once review_integrity has
    run; the signal-count heuristic is the fallback until then."""

    verdict: Literal["clear", "warn", "flagged", "pending"]
    # False when the requisition's proctoring toggle was off — the review UI
    # shows "proctoring off" instead of a (vacuously) clean camera record.
    proctoring_enabled: bool = True
    frame_count: int
    analyzed_count: int
    signal_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}  # by severity
    identity_verdict: str | None = None
    score: int | None = None  # LLM integrity score, higher = cleaner
    band: str | None = None  # "90-100" | "60-89" | "40-59" | "under-40"
    summary: str | None = None  # LLM reviewer's 2-3 sentence rationale


def integrity_verdict(
    signal_counts: dict[str, int],
    event_counts: dict[str, int],
    frame_count: int,
    analyzed_count: int,
    score: int | None = None,
) -> str:
    """Pure aggregation → verdict; unit-tested in tests/test_recording.py.
    An LLM integrity score takes precedence (band → chip color); the
    signal/event heuristic covers interviews reviewed before it lands."""
    if score is not None:
        band = integrity_band(score)
        return {"90-100": "clear", "60-89": "warn"}.get(band, "flagged")
    if frame_count > 0 and analyzed_count == 0:
        return "pending"
    if (
        signal_counts.get("multiple_faces")
        or signal_counts.get("no_face")
        or event_counts.get("high")
    ):
        return "flagged"
    if (
        signal_counts.get("attention_shift")
        or signal_counts.get("low_light")
        or event_counts.get("medium")
    ):
        return "warn"
    return "clear"


class ReviewTrailOut(BaseModel):
    at: datetime
    actor: str
    action: str
    detail: str | None = None


class ConsoleReviewOut(ConsoleInterviewOut):
    recommendation: str | None = None
    review_decision: str | None = None  # same as decision; kept for the review page wire shape
    assessment_summary: str | None = None
    review_notes: str | None = None
    percentile: int | None = None
    comparison_scores: list[float] = []
    audio_url: str | None = None
    waveform: dict | None = None
    # Presigned URL of the candidate's verification selfie (taken in the lobby
    # device check, independent of the proctoring toggle).
    selfie_url: str | None = None
    transcript: list[TranscriptTurnOut] = []
    screening_answers: list[ScreeningAnswerOut] = []
    rubric: list[RubricAssessmentOut] = []
    # Proctor frames are paginated separately (GET …/{id}/snapshots).
    integrity: IntegrityOut | None = None
    review_trail: list[ReviewTrailOut] = []


class WeeklyPointOut(BaseModel):
    week_start: str  # ISO date of the Monday
    count: int


class ConsoleDashboardOut(BaseModel):
    completed_total: int
    completed_delta_pct: float | None = None
    average_score: float | None = None
    active_requisitions: int
    domain_count: int
    weekly_completed: list[WeeklyPointOut]
    weekly_dropped: list[WeeklyPointOut]
    recent_interviews: list[ConsoleInterviewOut]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
async def _org_id_for(db: AsyncSession, user: AuthUser):
    from app.api.admin import _org_id_for as resolve

    return await resolve(db, user)


def _candidate_name(user_row: User | None) -> str:
    if user_row is None:
        return "Unknown"
    return user_row.display_name or user_row.email.split("@")[0]


# Friendly review-trail detail for interviews.end_reason.
_END_REASON_LABELS = {
    "completed": "Completed",
    "time_cap": "Time cap reached",
    "abandoned": "Abandoned",
    "error": "Ended due to error",
    "admin_terminated": "Terminated by admin",
}


def _answer_present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def _format_screening_answer(value, field_type: str) -> str | None:
    if not _answer_present(value):
        return None
    if field_type == "file":
        return "File uploaded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip()) or None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _screening_answers(
    submission: FormSubmission | None,
    template: FormTemplate | None,
    file: StoredFile | None = None,
    file_url: str | None = None,
) -> list[ScreeningAnswerOut]:
    if submission is None or template is None:
        return []
    schema = template.schema or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    order = (schema.get("x-kandidly") or {}).get("field_order") or list(properties)
    answers = submission.answers or {}

    rows: list[ScreeningAnswerOut] = []
    for key in order:
        prop = properties.get(key)
        if not isinstance(prop, dict):
            continue
        field_type = prop.get("x-builder-type") or prop.get("x-field") or prop.get("type") or "text"
        value = answers.get(key)
        is_file = str(field_type) == "file"
        answered = _answer_present(value) or (is_file and file is not None)
        answer = _format_screening_answer(value, str(field_type))
        if is_file and file is not None:
            answer = "File uploaded"
        file_ext = file.key.rsplit(".", 1)[-1] if is_file and file is not None else None
        rows.append(
            ScreeningAnswerOut(
                key=key,
                label=prop.get("title") or prop.get("x-label") or key,
                field_type=str(field_type),
                required=key in required,
                answered=answered,
                answer=answer,
                file_url=file_url if is_file else None,
                file_mime=file.mime if is_file and file is not None else None,
                file_name=f"{prop.get('title') or key}.{file_ext}" if file_ext else None,
            )
        )
    return rows


async def _req_stats(db: AsyncSession, req_ids: list[UUID]) -> tuple[dict, dict, dict]:
    """Per-requisition (clicks, completed count, newest open link token)."""
    if not req_ids:
        return {}, {}, {}
    link_rows = (
        await db.execute(
            select(InviteLink)
            .where(InviteLink.requisition_id.in_(req_ids))
            .order_by(InviteLink.created_at.desc())
        )
    ).scalars()
    clicks: dict[UUID, int] = {}
    tokens: dict[UUID, str] = {}
    for link in link_rows:
        clicks[link.requisition_id] = clicks.get(link.requisition_id, 0) + link.click_count
        if link.requisition_id not in tokens and link.kind == "open" and link.revoked_at is None:
            tokens[link.requisition_id] = link.token
    completed_rows = (
        await db.execute(
            select(Application.requisition_id, func.count())
            .where(
                Application.requisition_id.in_(req_ids),
                Application.state.in_(_COMPLETED_STATES),
            )
            .group_by(Application.requisition_id)
        )
    ).all()
    completed = {row[0]: row[1] for row in completed_rows}
    return clicks, completed, tokens


def _req_card(r: Requisition, clicks: dict, completed: dict, tokens: dict) -> ConsoleRequisitionOut:
    return ConsoleRequisitionOut(
        id=r.id,
        code=r.code,
        title=r.title,
        domain=r.domain,
        technical_requirements=list(r.technical_requirements or []),
        status=r.status,
        live=r.status == "open",
        opens_at=r.opens_at,
        closes_at=r.closes_at,
        created_at=r.created_at,
        invite_token=tokens.get(r.id),
        invite_only=InterviewConfig(**(r.interview_config or {})).invite_only,
        clicks=clicks.get(r.id, 0),
        completed=completed.get(r.id, 0),
    )


def _closes_at_from(end_date: str | None) -> datetime | None:
    """The link stays usable through the chosen end date/time (UTC)."""
    if not end_date:
        return None
    value = end_date.strip()
    if "T" in value or " " in value:
        dt = datetime.fromisoformat(value.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    else:
        return datetime.fromisoformat(value).replace(hour=23, minute=59, second=59, tzinfo=UTC)


def _proctoring_config(enabled: bool) -> ProctoringConfig:
    return ProctoringConfig(enabled=enabled, snapshot_interval_s=settings.snapshot_interval_s)


def _builder_is_valid(body: ConsoleRequisitionIn, schema: dict) -> bool:
    """Whether the builder payload is fully deployable — mirrors the client-side
    error list (and _create_template_and_rubric's checks). Used to decide draft
    vs offline on a non-deploy save: an unresolved error such as removing every
    must-have skill must persist the requisition as a draft, even when it does
    not change the versioned template/rubric artifacts."""
    try:
        if not body.title.strip() or not body.domain.strip() or not body.skills:
            raise AppError("validation_error", "incomplete requisition")
        if any(not c.description.strip() for c in body.rubric):
            raise AppError("validation_error", "every rubric criterion needs a description")
        validate_template(schema)
        validate_criteria(
            builder_rubric_to_criteria([c.model_dump() for c in body.rubric], is_draft=False)
        )
    except AppError:
        return False
    return True


async def _upsert_catalog(db: AsyncSession, org_id, user: AuthUser, body: ConsoleRequisitionIn):
    from app.api.admin import _upsert_catalog as upsert

    await upsert(
        db,
        org_id,
        user,
        [("domain", body.domain), ("job_title", body.title)] + [("skill", s) for s in body.skills],
    )


async def _create_template_and_rubric(
    db: AsyncSession, org_id, user: AuthUser, body: ConsoleRequisitionIn, family: tuple | None
) -> tuple[FormTemplate, Rubric, str]:
    """Create published template + rubric rows from builder payloads. `family`
    carries (template_family, template_version, rubric_family, rubric_version)
    when versioning an existing requisition's artifacts."""
    schema = builder_fields_to_schema([f.model_dump() for f in body.screening_fields])

    # Mirrors the builder's client-side error list: any failure keeps the
    # artifacts (and thus the requisition) in draft; deploys surface the error.
    is_valid = True
    try:
        if not body.title.strip():
            raise AppError("validation_error", "job title is required")
        if not body.domain.strip():
            raise AppError("validation_error", "domain is required")
        if not body.skills:
            raise AppError("validation_error", "at least one must-have skill is required")
        if any(not c.description.strip() for c in body.rubric):
            raise AppError("validation_error", "every rubric criterion needs a description")
        validate_template(schema)
        test_criteria = builder_rubric_to_criteria(
            [c.model_dump() for c in body.rubric], is_draft=False
        )
        validate_criteria(test_criteria)
    except AppError:
        if body.deploy:
            raise
        is_valid = False

    status = "published" if is_valid else "draft"
    criteria = builder_rubric_to_criteria(
        [c.model_dump() for c in body.rubric], is_draft=not is_valid
    )

    now = datetime.now(UTC)
    template = FormTemplate(
        id=new_id(),
        org_id=org_id,
        family_id=family[0] if family else new_id(),
        version=(family[1] + 1) if family else 1,
        interview_type="console_screen",
        title=f"{body.title} Screening Form",
        schema=schema,
        field_hints={"full_name": {"use_in_plan": False}},
        status=status,
        created_by=user.user_id,
        published_at=now if status == "published" else None,
    )
    db.add(template)
    rubric = Rubric(
        id=new_id(),
        org_id=org_id,
        family_id=family[2] if family else new_id(),
        version=(family[3] + 1) if family else 1,
        interview_type="console_screen",
        title=f"{body.title} Rubric",
        status=status,
        created_by=user.user_id,
        published_at=now if status == "published" else None,
    )
    db.add(rubric)
    await db.flush()
    for c in criteria:
        db.add(RubricCriterion(id=new_id(), rubric_id=rubric.id, **c))
    return template, rubric, status


# --------------------------------------------------------------------------- #
# account & usage (profile modal)
# --------------------------------------------------------------------------- #
class AccountOut(BaseModel):
    name: str
    email: str
    role: str
    org_name: str
    avatar_url: str | None = None
    plan: str = "free"


class UsageOut(BaseModel):
    plan: str = "free"
    requisitions_used: int
    requisitions_limit: int
    interviews_used: int
    interviews_limit: int
    # cumulative interviews at which candidate attempts go on hold (ER0402)
    interviews_hold_at: int


@router.get("/me", response_model=AccountOut)
async def get_account(user: AuthUser = _admin, db: AsyncSession = Depends(get_db)) -> AccountOut:
    org_id = await _org_id_for(db, user)
    org = await db.get(Organization, org_id)
    row = await db.get(User, user.user_id)
    return AccountOut(
        name=(row.display_name if row else None) or user.email.split("@")[0].title(),
        email=user.email,
        role=user.role,
        org_name=org.name if org else "—",
        avatar_url=row.avatar_url if row else None,
    )


@router.get("/usage", response_model=UsageOut)
async def get_usage(user: AuthUser = _admin, db: AsyncSession = Depends(get_db)) -> UsageOut:
    org_id = await _org_id_for(db, user)
    return UsageOut(
        requisitions_used=await requisition_count(db, org_id),
        requisitions_limit=settings.free_plan_max_requisitions,
        interviews_used=await interview_count(db, org_id),
        interviews_limit=settings.free_plan_max_interviews,
        interviews_hold_at=settings.free_plan_interview_hold_at,
    )


# --------------------------------------------------------------------------- #
# catalog
# --------------------------------------------------------------------------- #
@router.get("/catalog", response_model=CatalogOut)
async def get_catalog(user: AuthUser = _admin, db: AsyncSession = Depends(get_db)) -> CatalogOut:
    org_id = await _org_id_for(db, user)
    rows = (
        await db.execute(
            select(CatalogEntry.kind, CatalogEntry.value)
            .where(CatalogEntry.org_id == org_id)
            .order_by(CatalogEntry.value)
        )
    ).all()
    by_kind: dict[str, list[str]] = {"domain": [], "skill": [], "job_title": []}
    for kind, value in rows:
        by_kind.setdefault(kind, []).append(value)
    return CatalogOut(
        domains=by_kind["domain"], skills=by_kind["skill"], job_titles=by_kind["job_title"]
    )


# --------------------------------------------------------------------------- #
# requisitions
# --------------------------------------------------------------------------- #
@router.get("/requisitions", response_model=list[ConsoleRequisitionOut])
async def list_console_requisitions(
    user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> list[ConsoleRequisitionOut]:
    org_id = await _org_id_for(db, user)
    reqs = (
        (
            await db.execute(
                select(Requisition)
                .where(Requisition.org_id == org_id, Requisition.deleted_at.is_(None))
                .order_by(Requisition.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    clicks, completed, tokens = await _req_stats(db, [r.id for r in reqs])
    return [_req_card(r, clicks, completed, tokens) for r in reqs]


async def _detail_out(db: AsyncSession, r: Requisition) -> ConsoleRequisitionDetailOut:
    clicks, completed, tokens = await _req_stats(db, [r.id])
    card = _req_card(r, clicks, completed, tokens)
    template = await db.get(FormTemplate, r.form_template_id)
    criteria = (
        (
            await db.execute(
                select(RubricCriterion)
                .where(RubricCriterion.rubric_id == r.rubric_id)
                .order_by(RubricCriterion.display_order)
            )
        )
        .scalars()
        .all()
    )
    cfg = InterviewConfig(**(r.interview_config or {}))
    return ConsoleRequisitionDetailOut(
        **card.model_dump(),
        objective=r.role_objective,
        tone=cfg.tone,
        end_date=r.end_date.isoformat() if r.end_date else None,
        proctoring_enabled=cfg.proctoring.enabled,
        duration_minutes=cfg.max_duration_seconds // 60,
        sample_questions=[BuilderQuestion(**q) for q in (r.sample_questions or [])],
        screening_fields=[
            BuilderField(**f)
            for f in schema_to_builder_fields(template.schema if template else {})
            if f["id"] != "full_name"  # injected server-side; not builder-editable
        ],
        rubric=[
            BuilderCriterion(
                id=c.key, name=c.name, description=c.description, weight=float(c.weight)
            )
            for c in criteria
        ],
    )


async def _get_live_requisition(db: AsyncSession, req_id: UUID, org_id: UUID) -> Requisition:
    """Fetch for view/edit — soft-deleted or another org's requisition is gone
    (404 either way; existence must not leak across tenants)."""
    req = await db.get(Requisition, req_id)
    if req is None or req.deleted_at is not None or req.org_id != org_id:
        raise AppError("not_found", "Requisition not found")
    return req


@router.get("/requisitions/{req_id}", response_model=ConsoleRequisitionDetailOut)
async def get_console_requisition(
    req_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ConsoleRequisitionDetailOut:
    req = await _get_live_requisition(db, req_id, await _org_id_for(db, user))
    return await _detail_out(db, req)


@router.post("/requisitions", response_model=ConsoleRequisitionDetailOut)
async def deploy_requisition(
    body: ConsoleRequisitionIn, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ConsoleRequisitionDetailOut:
    """Composite deploy: published template + rubric + requisition + open
    invite link in one transaction (the builder's Deploy / Save-as-Offline)."""
    import asyncio

    await asyncio.sleep(3)
    org_id = await _org_id_for(db, user)
    # Free-plan quota: creating a requisition past the cap is refused (402).
    await ensure_can_create_requisition(db, org_id, deploy=body.deploy)
    template, rubric, artifact_status = await _create_template_and_rubric(
        db, org_id, user, body, family=None
    )

    seq = (await db.execute(sa_text("SELECT nextval('requisition_code_seq')"))).scalar_one()

    if body.deploy:
        req_status = "open"
    else:
        req_status = "paused" if artifact_status == "published" else "draft"

    req = Requisition(
        id=new_id(),
        org_id=org_id,
        code=f"REQ-{seq:04d}",
        title=body.title,
        interview_type="console_screen",
        domain=body.domain,
        technical_requirements=list(body.skills),
        role_objective=body.objective or None,
        sample_questions=[q.model_dump() for q in body.sample_questions],
        form_template_id=template.id,
        rubric_id=rubric.id,
        status=req_status,
        interview_config=InterviewConfig(
            tone=body.tone,
            max_duration_seconds=body.duration_minutes * 60,
            proctoring=_proctoring_config(body.proctoring_enabled),
            invite_only=body.invite_only,
        ).model_dump(),
        created_by=user.user_id,
        opens_at=datetime.now(UTC) if body.deploy else None,
        closes_at=_closes_at_from(body.end_date),
        end_date=_closes_at_from(body.end_date),
    )
    db.add(req)
    await db.flush()
    db.add(
        InviteLink(
            id=new_id(),
            requisition_id=req.id,
            token=generate_token(),
            kind="open",
            created_by=user.user_id,
        )
    )
    await db.flush()  # autoflush is off; _detail_out re-selects the link
    await _upsert_catalog(db, org_id, user, body)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="requisition.deploy" if body.deploy else "requisition.save_draft",
        entity_type="requisition",
        entity_id=req.id,
    )
    # See update_requisition: commit before returning so the just-created
    # requisition is durable before the response (and any immediate re-read).
    await db.commit()
    return await _detail_out(db, req)


@router.put("/requisitions/{req_id}", response_model=ConsoleRequisitionDetailOut)
async def update_requisition(
    req_id: UUID,
    body: ConsoleRequisitionIn,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> ConsoleRequisitionDetailOut:
    """Builder save on an existing requisition. Templates/rubrics are
    immutable versions: changed screening fields or rubric produce a new
    published version and repoint the requisition."""
    import asyncio

    await asyncio.sleep(3)
    org_id = await _org_id_for(db, user)
    req = await _get_live_requisition(db, req_id, org_id)

    current_template = await db.get(FormTemplate, req.form_template_id)
    current_rubric = await db.get(Rubric, req.rubric_id)
    current_criteria = (
        (
            await db.execute(
                select(RubricCriterion)
                .where(RubricCriterion.rubric_id == req.rubric_id)
                .order_by(RubricCriterion.display_order)
            )
        )
        .scalars()
        .all()
    )

    new_schema = builder_fields_to_schema([f.model_dump() for f in body.screening_fields])
    new_criteria = builder_rubric_to_criteria([c.model_dump() for c in body.rubric], is_draft=True)
    schema_changed = current_template is None or current_template.schema != new_schema
    rubric_changed = [(c.name, c.description, float(c.weight)) for c in current_criteria] != [
        (c["name"], c["description"], float(c["weight"])) for c in new_criteria
    ]
    force_new_version = (current_template is not None and current_template.status == "draft") or (
        current_rubric is not None and current_rubric.status == "draft"
    )

    if schema_changed or rubric_changed or force_new_version:
        template, rubric, _ = await _create_template_and_rubric(
            db,
            org_id,
            user,
            body,
            family=(
                current_template.family_id if current_template else new_id(),
                current_template.version if current_template else 0,
                current_rubric.family_id if current_rubric else new_id(),
                current_rubric.version if current_rubric else 0,
            ),
        )
        req.form_template_id = template.id
        req.rubric_id = rubric.id

    req.title = body.title
    req.domain = body.domain
    req.technical_requirements = list(body.skills)
    req.role_objective = body.objective or None
    req.sample_questions = [q.model_dump() for q in body.sample_questions]
    cfg = InterviewConfig(**(req.interview_config or {}))
    req.interview_config = cfg.model_copy(
        update={
            "tone": body.tone,
            "max_duration_seconds": body.duration_minutes * 60,
            "proctoring": _proctoring_config(body.proctoring_enabled),
            "invite_only": body.invite_only,
        }
    ).model_dump()
    req.closes_at = _closes_at_from(body.end_date)
    req.end_date = _closes_at_from(body.end_date)
    if body.deploy:
        req.status = "open"
        req.opens_at = req.opens_at or datetime.now(UTC)
    else:
        # Draft vs offline tracks the whole payload's validity (including
        # skills), not just whether the versioned artifacts changed — otherwise
        # clearing all skills leaves a stale "paused" status behind.
        req.status = "paused" if _builder_is_valid(body, new_schema) else "draft"
    req.updated_at = datetime.now(UTC)

    await _upsert_catalog(db, org_id, user, body)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="requisition.update",
        entity_type="requisition",
        entity_id=req.id,
        meta={"new_versions": schema_changed or rubric_changed},
    )
    # Commit before returning: under Starlette's yield-dependency teardown the
    # get_db() commit runs *after* the response is sent, so a client that
    # immediately re-opens the builder would read pre-commit state (e.g. skills
    # it just cleared reappear). Committing here makes the save read-your-write.
    await db.commit()
    # Invites collected while the requisition was a draft stay 'queued' so no
    # one is emailed a dead link; deploying releases them (post-commit: the
    # worker must see the rows).
    if req.status == "open":
        await _enqueue_queued_invite_emails(db, req.id)
    return await _detail_out(db, req)


@router.delete("/requisitions/{req_id}")
async def delete_requisition(
    req_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> dict:
    """Soft delete (irreversible from the UI): the requisition disappears from
    every console/admin read and its invite links stop resolving ('closed'),
    while interviews taken against it keep their requisition_id and stay in
    the ledger."""
    req = await _get_live_requisition(db, req_id, await _org_id_for(db, user))
    now = datetime.now(UTC)
    req.deleted_at = now
    req.status = "closed"
    req.updated_at = now
    await record_audit(
        db,
        actor_id=user.user_id,
        action="requisition.delete",
        entity_type="requisition",
        entity_id=req.id,
    )
    # Same read-your-write rationale as update_requisition: commit before the
    # response so the requisitions list refetch can't see the pre-delete row.
    await db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# interviews ledger + review
# --------------------------------------------------------------------------- #
def _ledger_row(
    interview: Interview,
    candidate: User | None,
    req: Requisition,
    report: Report | None,
) -> ConsoleInterviewOut:
    # Human review decision only — the AI hint stays on the review page as
    # `recommendation`, never in the ledger's decision column.
    decision = report.review_decision if report else None
    return ConsoleInterviewOut(
        id=interview.id,
        code=interview.code,
        candidate_name=_candidate_name(candidate),
        candidate_email=candidate.email if candidate else None,
        requisition_code=req.code,
        requisition_title=req.title,
        domain=req.domain,
        scoring_status="done" if report else "evaluating",
        decision=decision,
        concluded_at=interview.ended_at,
        duration_seconds=interview.elapsed_active_seconds,
        final_score=float(report.overall_score) if report else None,
    )


async def _ledger_rows(
    db: AsyncSession, org_id: UUID, limit: int | None = None
) -> list[ConsoleInterviewOut]:
    stmt = (
        select(Interview, User, Requisition, Report)
        .join(Application, Application.id == Interview.application_id)
        .join(User, User.id == Application.candidate_id)
        .join(Requisition, Requisition.id == Interview.requisition_id)
        .outerjoin(Report, Report.interview_id == Interview.id)
        .where(Interview.ended_at.is_not(None), Requisition.org_id == org_id)
        .order_by(Interview.ended_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).all()
    return [_ledger_row(i, u, r, rep) for i, u, r, rep in rows]


async def _get_org_interview(db: AsyncSession, interview_id: UUID, user: AuthUser) -> Interview:
    """Interview lookup for review surfaces — another org's interview must 404
    identically to a missing one (tenant isolation with open signup)."""
    interview = await db.get(Interview, interview_id)
    req = await db.get(Requisition, interview.requisition_id) if interview else None
    if interview is None or req is None or req.org_id != await _org_id_for(db, user):
        raise AppError("not_found", "Interview not found")
    return interview


@router.get("/interviews", response_model=list[ConsoleInterviewOut])
async def list_console_interviews(
    user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> list[ConsoleInterviewOut]:
    return await _ledger_rows(db, await _org_id_for(db, user))


@router.get("/interviews/{interview_id}", response_model=ConsoleReviewOut)
async def get_console_review(
    interview_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ConsoleReviewOut:
    interview = await _get_org_interview(db, interview_id, user)
    app = await db.get(Application, interview.application_id)
    candidate = await db.get(User, app.candidate_id) if app else None
    req = await db.get(Requisition, interview.requisition_id)
    report = (
        await db.execute(select(Report).where(Report.interview_id == interview.id))
    ).scalar_one_or_none()

    base = _ledger_row(interview, candidate, req, report)  # type: ignore[arg-type]

    submission: FormSubmission | None = None
    template: FormTemplate | None = None
    screening_file: StoredFile | None = None
    screening_file_url: str | None = None
    if app is not None:
        submission = (
            await db.execute(select(FormSubmission).where(FormSubmission.application_id == app.id))
        ).scalar_one_or_none()
        if submission is not None:
            template = await db.get(FormTemplate, submission.template_id)
            if submission.resume_file_id is not None:
                screening_file = await db.get(StoredFile, submission.resume_file_id)
                if screening_file is not None:
                    screening_file_url = await storage.presign_get(
                        screening_file.bucket,
                        screening_file.key,
                        public=True,
                    )
    screening_answers = _screening_answers(
        submission,
        template,
        file=screening_file,
        file_url=screening_file_url,
    )

    # Transcript with offsets from interview start.
    turns = (
        (await db.execute(select(Turn).where(Turn.interview_id == interview.id).order_by(Turn.seq)))
        .scalars()
        .all()
    )
    start = interview.started_at
    transcript = [
        TranscriptTurnOut(
            id=t.id,
            seconds=max(0, int((t.started_at - start).total_seconds())) if start else 0,
            speaker=t.speaker,
            text=t.text,
        )
        for t in turns
        if t.speaker in ("kandidly", "candidate")
    ]

    # Rubric assessment: evaluations joined with criterion names/weights.
    rubric_rows: list[RubricAssessmentOut] = []
    if req is not None:
        pairs = (
            await db.execute(
                sa_text(
                    """
                    SELECT rc.key, rc.name, rc.weight, ev.final_score, ev.rationale, ev.evidence
                    FROM evaluations ev
                    JOIN rubric_criteria rc
                      ON rc.rubric_id = :rubric_id AND rc.key = ev.criterion_key
                    WHERE ev.interview_id = :interview_id
                    ORDER BY rc.display_order
                    """
                ),
                {"rubric_id": str(req.rubric_id), "interview_id": str(interview.id)},
            )
        ).all()
        import json as _json

        for key, name, weight, final_score, rationale, evidence in pairs:
            quotes = [
                e.get("quote", "")
                for e in (evidence if isinstance(evidence, list) else _json.loads(evidence or "[]"))
                if isinstance(e, dict) and e.get("quote")
            ]
            reasoning = rationale + (
                (" Evidence: " + " / ".join(f"“{q}”" for q in quotes)) if quotes else ""
            )
            rubric_rows.append(
                RubricAssessmentOut(
                    key=key,
                    label=name,
                    weight=float(weight),
                    score=float(final_score),
                    summary=rationale,
                    reasoning=reasoning,
                )
            )

    # Percentile vs same-requisition cohort.
    percentile: int | None = None
    comparison: list[float] = []
    if report is not None and req is not None:
        cohort = (
            await db.execute(
                select(Report.overall_score)
                .join(Interview, Interview.id == Report.interview_id)
                .where(Interview.requisition_id == req.id)
                .order_by(Report.overall_score)
            )
        ).scalars()
        comparison = [float(s) for s in cohort]
        n_others = len(comparison) - 1
        if n_others > 0:
            below = sum(1 for s in comparison if s < float(report.overall_score))
            percentile = round(100 * below / n_others)
        else:
            percentile = 50

    # Audio: presigned URL (browser-reachable endpoint) + stored peaks.
    audio_url: str | None = None
    if interview.audio_recording_id is not None:
        f = await db.get(StoredFile, interview.audio_recording_id)
        if f is not None:
            audio_url = await storage.presign_get(f.bucket, f.key, public=True)

    # Verification selfie from the lobby device check (fixed per-application key).
    selfie_url: str | None = None
    if app is not None:
        selfie_file = (
            await db.execute(
                select(StoredFile).where(
                    StoredFile.bucket == storage.BUCKET_SELFIES,
                    StoredFile.key == storage.selfie_key(app.id),
                )
            )
        ).scalar_one_or_none()
        if selfie_file is not None:
            selfie_url = await storage.presign_get(selfie_file.bucket, selfie_file.key, public=True)

    # Integrity aggregation over the full snapshot set (the filmstrip itself
    # is served paginated by console_review_snapshots).
    snap_rows = (
        await db.execute(
            select(ProctoringSnapshot.analyzed, ProctoringSnapshot.signal).where(
                ProctoringSnapshot.interview_id == interview.id
            )
        )
    ).all()
    frame_count = len(snap_rows)
    analyzed_count = sum(1 for analyzed, _signal in snap_rows if analyzed)
    signal_counts: dict[str, int] = {}
    for _analyzed, signal in snap_rows:
        if signal:
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
    event_counts: dict[str, int] = {}
    for severity, count in await db.execute(
        select(ProctoringEvent.severity, func.count())
        .where(ProctoringEvent.interview_id == interview.id)
        .group_by(ProctoringEvent.severity)
    ):
        event_counts[severity] = count
    identity = (
        await db.execute(select(IdentityCheck).where(IdentityCheck.interview_id == interview.id))
    ).scalar_one_or_none()
    from app.domain.proctoring import config_for as proctoring_config_for

    review = interview.integrity_review or {}
    integrity = IntegrityOut(
        verdict=integrity_verdict(  # type: ignore[arg-type]
            signal_counts,
            event_counts,
            frame_count,
            analyzed_count,
            score=interview.integrity_score,
        ),
        proctoring_enabled=proctoring_config_for(req.interview_config if req else None).enabled,
        frame_count=frame_count,
        analyzed_count=analyzed_count,
        signal_counts=signal_counts,
        event_counts=event_counts,
        identity_verdict=identity.verdict if identity else None,
        score=interview.integrity_score,
        band=integrity_band(interview.integrity_score)
        if interview.integrity_score is not None
        else None,
        summary=review.get("summary"),
    )

    # Review trail: invitation → interview start/end → evaluation milestone,
    # plus audit-log report actions. Rendered newest-first in the console.
    trail: list[ReviewTrailOut] = []
    # Invitation time: guest-list entry for this candidate's email, falling
    # back to a personal invite link. Open-link walk-ins have no invitation.
    invited = False
    if candidate is not None:
        invite_row = (
            await db.execute(
                select(RequisitionInvite, User)
                .outerjoin(User, User.id == RequisitionInvite.invited_by)
                .where(
                    RequisitionInvite.requisition_id == interview.requisition_id,
                    RequisitionInvite.email == candidate.email.strip().lower(),
                )
            )
        ).first()
        if invite_row is not None:
            invite, inviter = invite_row
            invited = True
            trail.append(
                ReviewTrailOut(
                    at=invite.last_emailed_at or invite.created_at,
                    actor=_candidate_name(inviter) if inviter else "system",
                    action="candidate.invited",
                    detail=invite.email,
                )
            )
    if not invited and app is not None and app.invite_link_id is not None:
        link = await db.get(InviteLink, app.invite_link_id)
        if link is not None and link.kind == "personal":
            creator = await db.get(User, link.created_by)
            trail.append(
                ReviewTrailOut(
                    at=link.created_at,
                    actor=_candidate_name(creator) if creator else "system",
                    action="candidate.invited",
                    detail=link.email,
                )
            )
    if interview.started_at is not None:
        trail.append(
            ReviewTrailOut(
                at=interview.started_at,
                actor=_candidate_name(candidate),
                action="interview.started",
                detail=None,
            )
        )
    if interview.ended_at is not None:
        trail.append(
            ReviewTrailOut(
                at=interview.ended_at,
                actor=_candidate_name(candidate),
                action="interview.ended",
                detail=_END_REASON_LABELS.get(interview.end_reason or "", interview.end_reason),
            )
        )
    if report is not None:
        trail.append(
            ReviewTrailOut(
                at=report.created_at,
                actor="system",
                action="report.generated",
                detail=f"Overall score {float(report.overall_score):.1f}/100",
            )
        )
        audit_rows = (
            await db.execute(
                select(AuditLog, User)
                .outerjoin(User, User.id == AuditLog.actor_id)
                .where(AuditLog.entity_type == "report", AuditLog.entity_id == report.id)
                .order_by(AuditLog.created_at)
            )
        ).all()
        for entry, actor in audit_rows:
            trail.append(
                ReviewTrailOut(
                    at=entry.created_at,
                    actor=_candidate_name(actor) if actor else "system",
                    action=entry.action,
                    detail=(entry.meta or {}).get("decision"),
                )
            )
    # Latest activity first.
    trail.sort(key=lambda t: t.at, reverse=True)

    return ConsoleReviewOut(
        **base.model_dump(),
        recommendation=recommendation_for(float(report.overall_score)) if report else None,
        review_decision=report.review_decision if report else None,
        assessment_summary=report.summary if report else None,
        review_notes=report.review_notes if report else None,
        percentile=percentile,
        comparison_scores=comparison,
        audio_url=audio_url,
        waveform=interview.audio_waveform,
        selfie_url=selfie_url,
        transcript=transcript,
        screening_answers=screening_answers,
        rubric=rubric_rows,
        integrity=integrity,
        review_trail=trail,
    )


# Operator-only surface: interview deletion (destructive — DB + S3 + Redis,
# scoped after the 2026-07-19 stuck-interview incident) and the email smoke
# test (sends real mail in prod). Deliberately hardcoded to one account rather
# than a role, per explicit product decision: every other console user gets a
# 403 here even though they pass the `_admin` role guard.
_OPERATOR_EMAIL = "vishalkhare39@gmail.com"


async def _ensure_operator(db: AsyncSession, user: AuthUser, what: str) -> None:
    row = await db.get(User, user.user_id)
    email = (row.email if row else user.email) or ""
    if email.lower() != _OPERATOR_EMAIL:
        raise AppError("forbidden", f"{what} is not available for this account")


@router.delete("/interviews/{interview_id}")
async def delete_console_interview(
    interview_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> dict:
    """Hard delete an interview's DB rows, S3 objects, and Redis context cache
    — for clearing out runs corrupted by an infra bug (e.g. the agent never
    dispatching) so the candidate can attempt again. The owning application
    drops its interview_id and reverts to 'abandoned' (same direct-set
    shortcut past transition() that sweep_abandoned / dev_reset use), which
    clears it from the uq_app_live index so the next claim starts fresh."""
    await _ensure_operator(db, user, "Interview deletion")
    interview = await _get_org_interview(db, interview_id, user)

    snapshot_file_ids = (
        (
            await db.execute(
                select(ProctoringSnapshot.file_id).where(
                    ProctoringSnapshot.interview_id == interview_id
                )
            )
        )
        .scalars()
        .all()
    )
    report = (
        await db.execute(select(Report).where(Report.interview_id == interview_id))
    ).scalar_one_or_none()
    identity_check = (
        await db.execute(select(IdentityCheck).where(IdentityCheck.interview_id == interview_id))
    ).scalar_one_or_none()
    file_ids = set(snapshot_file_ids)
    if interview.audio_recording_id:
        file_ids.add(interview.audio_recording_id)
    if report and report.html_file_id:
        file_ids.add(report.html_file_id)
    if identity_check:
        file_ids.add(identity_check.reference_file_id)

    # Children first — none of these have ON DELETE CASCADE from interviews.
    # evidence_notes before turns (FK's to both interviews and turns);
    # turns/injections before question_plans (their node_id FKs question_plan_nodes,
    # which cascades from question_plans).
    await db.execute(sa_delete(EvidenceNote).where(EvidenceNote.interview_id == interview_id))
    await db.execute(sa_delete(Turn).where(Turn.interview_id == interview_id))
    await db.execute(sa_delete(Injection).where(Injection.interview_id == interview_id))
    await db.execute(sa_delete(ProctoringEvent).where(ProctoringEvent.interview_id == interview_id))
    await db.execute(
        sa_delete(ProctoringSnapshot).where(ProctoringSnapshot.interview_id == interview_id)
    )
    await db.execute(sa_delete(IdentityCheck).where(IdentityCheck.interview_id == interview_id))
    await db.execute(sa_delete(Evaluation).where(Evaluation.interview_id == interview_id))
    # ScoringJob -> CriterionScore cascades (ondelete=CASCADE).
    await db.execute(sa_delete(ScoringJob).where(ScoringJob.interview_id == interview_id))
    await db.execute(sa_delete(Report).where(Report.interview_id == interview_id))
    # QuestionPlan -> QuestionPlanNode cascades (ondelete=CASCADE).
    await db.execute(sa_delete(QuestionPlan).where(QuestionPlan.interview_id == interview_id))

    app = await db.get(Application, interview.application_id)
    if app:
        app.interview_id = None  # type: ignore
        app.state = "abandoned"
        # autoflush is off (app/db/session.py) — the raw DELETE below must not
        # race this pending UPDATE, or fk_app_interview blocks it.
        await db.flush()

    await db.execute(sa_delete(Interview).where(Interview.id == interview_id))
    # Stored files last: interviews.audio_recording_id references stored_files
    # with no ON DELETE, so deleting the recording's file before the interview
    # row is an FK violation (their other referencers — reports, identity
    # checks, snapshots — are already gone by this point).
    if file_ids:
        await db.execute(sa_delete(StoredFile).where(StoredFile.id.in_(file_ids)))
    await record_audit(
        db,
        actor_id=user.user_id,
        action="interview.deleted",
        entity_type="interview",
        entity_id=interview_id,
    )
    await db.commit()

    # Best-effort external cleanup after the DB commit succeeds — an orphaned
    # S3 object or stale cache entry is recoverable; a dangling DB reference
    # to a deleted row is not.
    for bucket in (storage.BUCKET_SNAPSHOTS, storage.BUCKET_RECORDINGS, storage.BUCKET_REPORTS):
        try:
            for key in await storage.list_keys(bucket, f"{interview_id}/"):
                await storage.delete_object(bucket, key)
        except Exception as exc:  # noqa: BLE001
            log.warning("interview_delete_storage_cleanup_failed", bucket=bucket, error=str(exc))
    await interview_context.invalidate(interview_id)

    return {"ok": True}


@router.get("/interviews/{interview_id}/snapshots", response_model=ProctorFramePageOut)
async def console_review_snapshots(
    interview_id: UUID,
    offset: int = 0,
    limit: int = 10,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> ProctorFramePageOut:
    """Filmstrip page for the review screen: every captured frame, capture
    order, presigned image URLs. Small pages keep presigning cheap; the client
    infinite-scrolls through them."""
    interview = await _get_org_interview(db, interview_id, user)
    offset = max(0, offset)
    limit = max(1, min(50, limit))
    start = interview.started_at
    total = (
        await db.execute(
            select(func.count())
            .select_from(ProctoringSnapshot)
            .where(ProctoringSnapshot.interview_id == interview.id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(ProctoringSnapshot, StoredFile)
            .join(StoredFile, StoredFile.id == ProctoringSnapshot.file_id)
            .where(ProctoringSnapshot.interview_id == interview.id)
            .order_by(ProctoringSnapshot.captured_at, ProctoringSnapshot.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = [
        ProctorFrameOut(
            id=snap.id,
            seconds=max(0, int((snap.captured_at - start).total_seconds())) if start else 0,
            signal=snap.signal,
            image_url=await storage.presign_get(f.bucket, f.key, public=True),
            analyzed=snap.analyzed,
            note=((snap.client_meta or {}).get("vision") or {}).get("note"),
        )
        for snap, f in rows
    ]
    return ProctorFramePageOut(items=items, total=total, offset=offset, limit=limit)


# --------------------------------------------------------------------------- #
# dashboard
# --------------------------------------------------------------------------- #
def _week_start(dt: datetime) -> datetime:
    monday = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday


@router.get("/dashboard", response_model=ConsoleDashboardOut)
async def get_dashboard(
    user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ConsoleDashboardOut:
    now = datetime.now(UTC)
    horizon = _week_start(now) - timedelta(weeks=11)
    org_id = await _org_id_for(db, user)

    ended = (
        await db.execute(
            select(Interview.ended_at, Interview.end_reason)
            .join(Requisition, Requisition.id == Interview.requisition_id)
            .where(Interview.ended_at.is_not(None), Requisition.org_id == org_id)
        )
    ).all()
    completed_total = len(ended)

    week_starts = [horizon + timedelta(weeks=i) for i in range(12)]
    completed_buckets = dict.fromkeys((w.date().isoformat() for w in week_starts), 0)
    dropped_buckets = dict.fromkeys((w.date().isoformat() for w in week_starts), 0)
    last7 = prev7 = 0
    for ended_at, end_reason in ended:
        if ended_at >= now - timedelta(days=7):
            last7 += 1
        elif ended_at >= now - timedelta(days=14):
            prev7 += 1
        key = _week_start(ended_at).date().isoformat()
        if key in completed_buckets:
            completed_buckets[key] += 1
            if end_reason == "abandoned":
                dropped_buckets[key] += 1

    delta_pct = round(100 * (last7 - prev7) / prev7, 1) if prev7 else None

    average_score = (
        await db.execute(
            select(func.avg(Report.overall_score))
            .join(Interview, Interview.id == Report.interview_id)
            .join(Requisition, Requisition.id == Interview.requisition_id)
            .where(Requisition.org_id == org_id)
        )
    ).scalar_one_or_none()

    active_reqs = (
        await db.execute(
            select(Requisition.domain).where(
                Requisition.status == "open", Requisition.org_id == org_id
            )
        )
    ).all()

    return ConsoleDashboardOut(
        completed_total=completed_total,
        completed_delta_pct=delta_pct,
        average_score=round(float(average_score), 1) if average_score is not None else None,
        active_requisitions=len(active_reqs),
        domain_count=len({d for (d,) in active_reqs if d}),
        weekly_completed=[
            WeeklyPointOut(week_start=k, count=v) for k, v in completed_buckets.items()
        ],
        weekly_dropped=[WeeklyPointOut(week_start=k, count=v) for k, v in dropped_buckets.items()],
        recent_interviews=await _ledger_rows(db, org_id, limit=8),
    )


# --------------------------------------------------------------------------- #
# Invite-only guest list (SPEC-adjacent; interview_config.invite_only)
# --------------------------------------------------------------------------- #
class InviteIn(BaseModel):
    email: str
    first_name: str = ""
    last_name: str = ""


class InvitesAddIn(BaseModel):
    invites: list[InviteIn] = Field(min_length=1, max_length=invites_domain.MAX_ROWS)


class InviteOut(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    # candidate_invite delivery: queued | sent | failed
    email_status: str
    last_emailed_at: datetime | None = None
    created_at: datetime
    # Pipeline progress derived from applications by candidate email.
    status: Literal["invited", "claimed", "completed"] = "invited"


class InvitesMutationOut(BaseModel):
    added: int
    duplicates: int
    invalid: list[dict] = []


async def _enqueue_queued_invite_emails(db: AsyncSession, req_id: UUID) -> None:
    ids = (
        (
            await db.execute(
                select(RequisitionInvite.id).where(
                    RequisitionInvite.requisition_id == req_id,
                    RequisitionInvite.email_status == "queued",
                    RequisitionInvite.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for invite_id in ids:
        await enqueue("send_invite_email", str(invite_id))


async def _add_invites(
    db: AsyncSession, req: Requisition, user: AuthUser, rows: list[dict]
) -> tuple[list[UUID], int]:
    """Upsert guest-list rows (emails pre-normalized); returns (ids to email,
    duplicates). Re-adding a revoked email reactivates it with a fresh send."""
    if not rows:
        return [], 0
    existing = {
        i.email: i
        for i in (
            await db.execute(
                select(RequisitionInvite).where(
                    RequisitionInvite.requisition_id == req.id,
                    RequisitionInvite.email.in_([r["email"] for r in rows]),
                )
            )
        ).scalars()
    }
    new_ids: list[UUID] = []
    duplicates = 0
    for row in rows:
        current = existing.get(row["email"])
        if current is not None and current.revoked_at is None:
            duplicates += 1
            continue
        if current is not None:
            current.revoked_at = None
            current.first_name = row["first_name"] or current.first_name
            current.last_name = row["last_name"] or current.last_name
            current.email_status = "queued"
            current.invited_by = user.user_id
            new_ids.append(current.id)
            continue
        invite = RequisitionInvite(
            id=new_id(),
            requisition_id=req.id,
            email=row["email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            invited_by=user.user_id,
        )
        db.add(invite)
        new_ids.append(invite.id)
    return new_ids, duplicates


class InvitesSearchOut(BaseModel):
    items: list[InviteOut]
    total: int  # active invites on the requisition (independent of the query)


@router.get("/requisitions/{req_id}/invites", response_model=InvitesSearchOut)
async def search_invites(
    req_id: UUID,
    q: str = "",
    limit: int = 3,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> InvitesSearchOut:
    """Autocomplete over the guest list: case-insensitive substring match on
    email and full name, newest first, capped at `limit`. The panel is
    search-first — an empty query returns only the total, never the list —
    so a multi-thousand guest list is never shipped to the browser."""
    req = await _get_live_requisition(db, req_id, await _org_id_for(db, user))
    active = (
        RequisitionInvite.requisition_id == req.id,
        RequisitionInvite.revoked_at.is_(None),
    )
    total = (
        await db.execute(select(func.count()).select_from(RequisitionInvite).where(*active))
    ).scalar_one()
    query = q.strip()
    if not query:
        return InvitesSearchOut(items=[], total=total)

    pattern = f"%{query}%"
    full_name = RequisitionInvite.first_name + " " + RequisitionInvite.last_name
    invites = (
        (
            await db.execute(
                select(RequisitionInvite)
                .where(
                    *active,
                    or_(RequisitionInvite.email.ilike(pattern), full_name.ilike(pattern)),
                )
                .order_by(RequisitionInvite.created_at.desc())
                .limit(max(1, min(limit, 10)))
            )
        )
        .scalars()
        .all()
    )
    # Pipeline progress only for the handful of matched emails.
    progress: dict[str, str] = {}
    if invites:
        app_rows = (
            await db.execute(
                select(func.lower(User.email), Application.state)
                .join(User, Application.candidate_id == User.id)
                .where(
                    Application.requisition_id == req.id,
                    func.lower(User.email).in_([i.email for i in invites]),
                )
            )
        ).all()
        for email, state in app_rows:
            if state in _COMPLETED_STATES or state == "completed":
                progress[email] = "completed"
            else:
                progress.setdefault(email, "claimed")
    return InvitesSearchOut(
        items=[
            InviteOut(
                id=i.id,
                email=i.email,
                first_name=i.first_name,
                last_name=i.last_name,
                email_status=i.email_status,
                last_emailed_at=i.last_emailed_at,
                created_at=i.created_at,
                status=progress.get(i.email, "invited"),  # type: ignore[arg-type]
            )
            for i in invites
        ],
        total=total,
    )


@router.post("/requisitions/{req_id}/invites", response_model=InvitesMutationOut)
async def add_invites(
    req_id: UUID,
    body: InvitesAddIn,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> InvitesMutationOut:
    req = await _get_live_requisition(db, req_id, await _org_id_for(db, user))
    rows: list[dict] = []
    invalid: list[dict] = []
    duplicates = 0
    seen: set[str] = set()
    for idx, invite in enumerate(body.invites, start=1):
        email = invites_domain.normalize_email(invite.email)
        if email is None:
            invalid.append({"row": idx, "reason": "invalid email"})
            continue
        if email in seen:
            duplicates += 1
            continue
        seen.add(email)
        rows.append(
            {
                "email": email,
                "first_name": invite.first_name.strip(),
                "last_name": invite.last_name.strip(),
            }
        )
    new_ids, dupes = await _add_invites(db, req, user, rows)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="invite.create",
        entity_type="requisition",
        entity_id=req.id,
        meta={"added": len(new_ids)},
    )
    # Commit before enqueueing: the worker must be able to load the rows.
    # Drafts stay 'queued' — deploy (update_requisition) releases them.
    await db.commit()
    if req.status == "open":
        for invite_id in new_ids:
            await enqueue("send_invite_email", str(invite_id))
    return InvitesMutationOut(added=len(new_ids), duplicates=duplicates + dupes, invalid=invalid)


@router.post(
    "/requisitions/{req_id}/invites/import",
    response_model=InvitesMutationOut,
    dependencies=[rate_limit("invite_import", 12)],
)
async def import_invites(
    req_id: UUID,
    file: UploadFile = File(...),
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> InvitesMutationOut:
    """Bulk upload: .csv or .xlsx with email / first name / last name columns
    (header row optional — without one, exactly that order)."""
    req = await _get_live_requisition(db, req_id, await _org_id_for(db, user))
    data = await file.read(invites_domain.MAX_FILE_BYTES + 1)
    try:
        parsed = invites_domain.parse_invite_file(file.filename or "", data)
    except ValueError as exc:
        raise AppError("validation_error", str(exc)) from exc
    new_ids, dupes = await _add_invites(db, req, user, parsed.rows)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="invite.import",
        entity_type="requisition",
        entity_id=req.id,
        meta={"added": len(new_ids), "invalid": len(parsed.invalid)},
    )
    await db.commit()
    if req.status == "open":
        for invite_id in new_ids:
            await enqueue("send_invite_email", str(invite_id))
    return InvitesMutationOut(
        added=len(new_ids), duplicates=parsed.duplicates + dupes, invalid=parsed.invalid
    )


async def _get_org_invite(db: AsyncSession, req: Requisition, invite_id: UUID) -> RequisitionInvite:
    invite = await db.get(RequisitionInvite, invite_id)
    if invite is None or invite.requisition_id != req.id or invite.revoked_at is not None:
        raise AppError("not_found", "Invite not found")
    return invite


@router.delete("/requisitions/{req_id}/invites/{invite_id}")
async def revoke_invite(
    req_id: UUID,
    invite_id: UUID,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Uninvite: blocks future claims only — an application already claimed
    (and any interview) lives on."""
    req = await _get_live_requisition(db, req_id, await _org_id_for(db, user))
    invite = await _get_org_invite(db, req, invite_id)
    invite.revoked_at = datetime.now(UTC)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="invite.revoke",
        entity_type="requisition",
        entity_id=req.id,
        meta={"email": invite.email},
    )
    return {"ok": True}


@router.post(
    "/requisitions/{req_id}/invites/{invite_id}/resend",
    dependencies=[rate_limit("invite_resend", 30)],
)
async def resend_invite(
    req_id: UUID,
    invite_id: UUID,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> dict:
    req = await _get_live_requisition(db, req_id, await _org_id_for(db, user))
    invite = await _get_org_invite(db, req, invite_id)
    invite.email_status = "queued"
    await record_audit(
        db,
        actor_id=user.user_id,
        action="invite.resend",
        entity_type="requisition",
        entity_id=req.id,
        meta={"email": invite.email},
    )
    await db.commit()
    if req.status == "open":
        await enqueue("send_invite_email", str(invite.id))
    return {"ok": True, "email_status": invite.email_status}


# --------------------------------------------------------------------------- #
# Org-wide invitations ledger (/console/invitations)
# --------------------------------------------------------------------------- #
class InvitationRowOut(BaseModel):
    id: UUID
    requisition_id: UUID
    requisition_code: str
    requisition_title: str
    email: str
    first_name: str
    last_name: str
    # candidate_invite delivery: queued | sent | failed
    email_status: str
    # Pipeline progress derived from applications by candidate email
    # (the UI labels these Invited / Attempting / Done).
    status: Literal["invited", "claimed", "completed"]
    created_at: datetime
    revoked_at: datetime | None = None


class InvitationsPageOut(BaseModel):
    items: list[InvitationRowOut]
    total: int  # rows matching the filters, across all pages
    offset: int
    limit: int


_INVITE_STAGES = {"invited": 0, "claimed": 1, "completed": 2}
_INVITE_STATUS_BY_STAGE = {v: k for k, v in _INVITE_STAGES.items()}


def _as_utc(dt: datetime) -> datetime:
    """created_at is timezone-aware; naive query bounds are taken as UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


@router.get("/invitations", response_model=InvitationsPageOut)
async def list_invitations(
    q: str = "",
    requisition_code: str = "",
    status: Literal["invited", "claimed", "completed"] | None = None,
    access: Literal["active", "revoked"] = "active",
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    offset: int = 0,
    limit: int = 20,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> InvitationsPageOut:
    """Every guest-list row across the org's live requisitions, newest first,
    with server-side filters + pagination (guest lists can run to thousands of
    rows, so this never ships the whole table). `status` is derived the same
    way as the per-requisition search: an application by the invited email
    marks it claimed, a completed/scored one marks it completed."""
    org_id = await _org_id_for(db, user)

    # (requisition, email) → furthest application stage, joined per invite row
    # so derived status is filterable in SQL rather than per page in Python.
    progress = (
        select(
            Application.requisition_id.label("req_id"),
            func.lower(User.email).label("email"),
            func.max(
                case((Application.state.in_([*_COMPLETED_STATES, "completed"]), 2), else_=1)
            ).label("stage"),
        )
        .join(User, User.id == Application.candidate_id)
        .group_by(Application.requisition_id, func.lower(User.email))
        .subquery()
    )
    stage = func.coalesce(progress.c.stage, 0)

    where = [
        Requisition.org_id == org_id,
        Requisition.deleted_at.is_(None),
        RequisitionInvite.revoked_at.is_(None)
        if access == "active"
        else RequisitionInvite.revoked_at.is_not(None),
    ]
    query = q.strip()
    if query:
        pattern = f"%{query}%"
        full_name = RequisitionInvite.first_name + " " + RequisitionInvite.last_name
        where.append(or_(RequisitionInvite.email.ilike(pattern), full_name.ilike(pattern)))
    if requisition_code.strip():
        where.append(Requisition.code.ilike(f"%{requisition_code.strip()}%"))
    if created_after is not None:
        where.append(RequisitionInvite.created_at >= _as_utc(created_after))
    if created_before is not None:
        where.append(RequisitionInvite.created_at <= _as_utc(created_before))
    if status is not None:
        where.append(stage == _INVITE_STAGES[status])

    base = (
        select(RequisitionInvite, Requisition.code, Requisition.title, stage.label("stage"))
        .join(Requisition, Requisition.id == RequisitionInvite.requisition_id)
        .outerjoin(
            progress,
            and_(
                progress.c.req_id == RequisitionInvite.requisition_id,
                progress.c.email == RequisitionInvite.email,
            ),
        )
        .where(*where)
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(RequisitionInvite.created_at.desc(), RequisitionInvite.id)
            .offset(max(0, offset))
            .limit(max(1, min(limit, 100)))
        )
    ).all()
    return InvitationsPageOut(
        items=[
            InvitationRowOut(
                id=invite.id,
                requisition_id=invite.requisition_id,
                requisition_code=req_code,
                requisition_title=req_title,
                email=invite.email,
                first_name=invite.first_name,
                last_name=invite.last_name,
                email_status=invite.email_status,
                status=_INVITE_STATUS_BY_STAGE[row_stage],  # type: ignore[arg-type]
                created_at=invite.created_at,
                revoked_at=invite.revoked_at,
            )
            for invite, req_code, req_title, row_stage in rows
        ],
        total=total,
        offset=max(0, offset),
        limit=max(1, min(limit, 100)),
    )


# --------------------------------------------------------------------------- #
# Email smoke test (operator-only)
# --------------------------------------------------------------------------- #
# Sample contexts so prod deliverability (DNS/DKIM, rendering across clients)
# can be checked without staging real invite data. The candidate-facing
# samples carry brand placeholders so the branded header/footer paths render
# in the smoke test too (brand integration is an upcoming feature).
_TEST_EMAIL_CONTEXTS: dict[str, dict] = {
    "org_invite": {
        "inviter_name": "Alex Rivera",
        "org_name": "Acme Talent",
        "accept_url": "{base}/console",
        "expiry_note": "This invitation expires in 7 days.",
    },
    "candidate_invite": {
        "org_name": "Acme Talent",
        "interview_name": "Backend Engineer Screen",
        "interview_url": "{base}/i/smoke-test-token",
        "candidate_name": "Jordan",
        "valid_until": "July 31, 2026",
        "brand_name": "Acme Talent",
        "brand_url": "https://example.com",
    },
    "interview_completed": {
        "candidate_name": "Jordan Lee",
        "org_name": "Acme Talent",
        "interview_name": "Backend Engineer Screen",
        "brand_name": "Acme Talent",
        "brand_url": "https://example.com",
    },
}


class TestEmailIn(BaseModel):
    template: Literal["org_invite", "candidate_invite", "interview_completed"]
    to: str = Field(min_length=3, pattern=r".+@.+")


@router.post("/email-test")
async def send_test_email(
    body: TestEmailIn, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> dict:
    """Render a template with sample context and send it synchronously (no arq
    hop) so the caller sees the transport result — or its error — right away."""
    from app.core import email as email_core

    await _ensure_operator(db, user, "The email smoke test")
    context = {
        k: v.format(base=settings.base_url_web) if isinstance(v, str) else v
        for k, v in _TEST_EMAIL_CONTEXTS[body.template].items()
    }
    rendered = email_core.render_email(body.template, context)
    try:
        message_id = await email_core.get_transport().send(to=body.to, message=rendered)
    except email_core.EmailSendError as exc:
        raise AppError("internal_error", f"Email send failed: {exc}") from exc
    await record_audit(
        db,
        actor_id=user.user_id,
        action="email.test_send",
        entity_type="email",
        entity_id=None,
        meta={"template": body.template, "to": body.to},
    )
    return {
        "transport": type(email_core.get_transport()).__name__,
        "message_id": message_id,
        "subject": rendered.subject,
    }
