"""Console API — serves the /console admin UI (dashboard, requisition grid +
builder, interviews ledger, interview review). Sits beside the SPEC §12.1
admin surface under /api/admin/console; same auth, audit on mutations.

Builder payload ↔ template/rubric mapping is pure logic in app.domain.builder.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import settings
from app.core.deps import get_db, require_role
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.security import AuthUser
from app.db.models import (
    Application,
    AuditLog,
    CatalogEntry,
    FormTemplate,
    IdentityCheck,
    Interview,
    InviteLink,
    Organization,
    ProctoringEvent,
    ProctoringSnapshot,
    Report,
    Requisition,
    Rubric,
    RubricCriterion,
    StoredFile,
    Turn,
    User,
)
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
    transcript: list[TranscriptTurnOut] = []
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


async def _get_live_requisition(db: AsyncSession, req_id: UUID) -> Requisition:
    """Fetch for view/edit — a soft-deleted requisition is gone (404)."""
    req = await db.get(Requisition, req_id)
    if req is None or req.deleted_at is not None:
        raise AppError("not_found", "Requisition not found")
    return req


@router.get("/requisitions/{req_id}", response_model=ConsoleRequisitionDetailOut)
async def get_console_requisition(
    req_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ConsoleRequisitionDetailOut:
    req = await _get_live_requisition(db, req_id)
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
    req = await _get_live_requisition(db, req_id)
    org_id = await _org_id_for(db, user)

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
    return await _detail_out(db, req)


@router.delete("/requisitions/{req_id}")
async def delete_requisition(
    req_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> dict:
    """Soft delete (irreversible from the UI): the requisition disappears from
    every console/admin read and its invite links stop resolving ('closed'),
    while interviews taken against it keep their requisition_id and stay in
    the ledger."""
    req = await _get_live_requisition(db, req_id)
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


async def _ledger_rows(db: AsyncSession, limit: int | None = None) -> list[ConsoleInterviewOut]:
    stmt = (
        select(Interview, User, Requisition, Report)
        .join(Application, Application.id == Interview.application_id)
        .join(User, User.id == Application.candidate_id)
        .join(Requisition, Requisition.id == Interview.requisition_id)
        .outerjoin(Report, Report.interview_id == Interview.id)
        .where(Interview.ended_at.is_not(None))
        .order_by(Interview.ended_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).all()
    return [_ledger_row(i, u, r, rep) for i, u, r, rep in rows]


@router.get("/interviews", response_model=list[ConsoleInterviewOut])
async def list_console_interviews(
    user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> list[ConsoleInterviewOut]:
    return await _ledger_rows(db)


@router.get("/interviews/{interview_id}", response_model=ConsoleReviewOut)
async def get_console_review(
    interview_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ConsoleReviewOut:
    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    app = await db.get(Application, interview.application_id)
    candidate = await db.get(User, app.candidate_id) if app else None
    req = await db.get(Requisition, interview.requisition_id)
    report = (
        await db.execute(select(Report).where(Report.interview_id == interview.id))
    ).scalar_one_or_none()

    base = _ledger_row(interview, candidate, req, report)  # type: ignore[arg-type]

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

    # Review trail from the audit log (report actions), plus scoring milestone.
    trail: list[ReviewTrailOut] = []
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
        transcript=transcript,
        rubric=rubric_rows,
        integrity=integrity,
        review_trail=trail,
    )


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
    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
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

    ended = (
        await db.execute(
            select(Interview.ended_at, Interview.end_reason).where(Interview.ended_at.is_not(None))
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

    average_score = (await db.execute(select(func.avg(Report.overall_score)))).scalar_one_or_none()

    active_reqs = (
        await db.execute(select(Requisition.domain).where(Requisition.status == "open"))
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
        recent_interviews=await _ledger_rows(db, limit=8),
    )
