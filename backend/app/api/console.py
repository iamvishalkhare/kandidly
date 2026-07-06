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
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.deps import get_db, require_role
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.security import AuthUser
from app.db.models import (
    Application,
    AuditLog,
    CatalogEntry,
    FormTemplate,
    Interview,
    InviteLink,
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
from app.domain.links import generate_token
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
    deploy: bool = True  # False → "Save as Offline" (draft)

    @field_validator("end_date")
    @classmethod
    def _end_date_iso(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            date.fromisoformat(v.strip())
        except ValueError as exc:
            raise ValueError("end_date must be an ISO date (YYYY-MM-DD)") from exc
        return v.strip()


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
    requisition_code: str
    requisition_title: str
    domain: str | None = None
    scoring_status: Literal["evaluating", "done"]
    decision: str | None = None  # human review decision, else AI recommendation
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


class ReviewTrailOut(BaseModel):
    at: datetime
    actor: str
    action: str
    detail: str | None = None


class ConsoleReviewOut(ConsoleInterviewOut):
    recommendation: str | None = None
    review_decision: str | None = None  # raw human decision (decision may be the AI hint)
    assessment_summary: str | None = None
    review_notes: str | None = None
    percentile: int | None = None
    comparison_scores: list[float] = []
    audio_url: str | None = None
    waveform: dict | None = None
    transcript: list[TranscriptTurnOut] = []
    rubric: list[RubricAssessmentOut] = []
    proctor_frames: list[ProctorFrameOut] = []
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
    """The link stays usable through the chosen end date (offline at the end
    of that day, UTC)."""
    if not end_date:
        return None
    return datetime.fromisoformat(end_date).replace(
        hour=23, minute=59, second=59, tzinfo=UTC
    )


def _proctoring_config(enabled: bool) -> ProctoringConfig:
    # Console proctoring captures a webcam frame every 10 seconds.
    return ProctoringConfig(enabled=enabled, snapshot_min_s=10, snapshot_max_s=10)


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
) -> tuple[FormTemplate, Rubric]:
    """Create published template + rubric rows from builder payloads. `family`
    carries (template_family, template_version, rubric_family, rubric_version)
    when versioning an existing requisition's artifacts."""
    schema = builder_fields_to_schema([f.model_dump() for f in body.screening_fields])
    validate_template(schema)
    criteria = builder_rubric_to_criteria([c.model_dump() for c in body.rubric])
    validate_criteria(criteria)

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
        status="published",
        created_by=user.user_id,
        published_at=now,
    )
    db.add(template)
    rubric = Rubric(
        id=new_id(),
        org_id=org_id,
        family_id=family[2] if family else new_id(),
        version=(family[3] + 1) if family else 1,
        interview_type="console_screen",
        title=f"{body.title} Rubric",
        status="published",
        created_by=user.user_id,
        published_at=now,
    )
    db.add(rubric)
    await db.flush()
    for c in criteria:
        db.add(RubricCriterion(id=new_id(), rubric_id=rubric.id, **c))
    return template, rubric


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
                .where(Requisition.org_id == org_id)
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
        end_date=(cfg.ends_at or "")[:10] or None,
        proctoring_enabled=cfg.proctoring.enabled,
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


@router.get("/requisitions/{req_id}", response_model=ConsoleRequisitionDetailOut)
async def get_console_requisition(
    req_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ConsoleRequisitionDetailOut:
    req = await db.get(Requisition, req_id)
    if req is None:
        raise AppError("not_found", "Requisition not found")
    return await _detail_out(db, req)


@router.post("/requisitions", response_model=ConsoleRequisitionDetailOut)
async def deploy_requisition(
    body: ConsoleRequisitionIn, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ConsoleRequisitionDetailOut:
    """Composite deploy: published template + rubric + requisition + open
    invite link in one transaction (the builder's Deploy / Save-as-Offline)."""
    org_id = await _org_id_for(db, user)
    template, rubric = await _create_template_and_rubric(db, org_id, user, body, family=None)

    seq = (await db.execute(sa_text("SELECT nextval('requisition_code_seq')"))).scalar_one()
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
        status="open" if body.deploy else "draft",
        interview_config=InterviewConfig(
            tone=body.tone,
            ends_at=body.end_date,
            proctoring=_proctoring_config(body.proctoring_enabled),
        ).model_dump(),
        created_by=user.user_id,
        opens_at=datetime.now(UTC) if body.deploy else None,
        closes_at=_closes_at_from(body.end_date),
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
    req = await db.get(Requisition, req_id)
    if req is None:
        raise AppError("not_found", "Requisition not found")
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
    new_criteria = builder_rubric_to_criteria([c.model_dump() for c in body.rubric])
    schema_changed = current_template is None or current_template.schema != new_schema
    rubric_changed = [(c.name, c.description, float(c.weight)) for c in current_criteria] != [
        (c["name"], c["description"], float(c["weight"])) for c in new_criteria
    ]

    if schema_changed or rubric_changed:
        template, rubric = await _create_template_and_rubric(
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
            "ends_at": body.end_date,
            "proctoring": _proctoring_config(body.proctoring_enabled),
        }
    ).model_dump()
    req.closes_at = _closes_at_from(body.end_date)
    if body.deploy and req.status in ("draft", "paused"):
        req.status = "open"
        req.opens_at = req.opens_at or datetime.now(UTC)
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
    return await _detail_out(db, req)


# --------------------------------------------------------------------------- #
# interviews ledger + review
# --------------------------------------------------------------------------- #
def _ledger_row(
    interview: Interview,
    candidate: User | None,
    req: Requisition,
    report: Report | None,
) -> ConsoleInterviewOut:
    decision = report.review_decision if report else None
    if decision is None and report is not None:
        decision = recommendation_for(float(report.overall_score))
    return ConsoleInterviewOut(
        id=interview.id,
        code=interview.code,
        candidate_name=_candidate_name(candidate),
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

    # Proctor frames with presigned snapshot images.
    snap_rows = (
        await db.execute(
            select(ProctoringSnapshot, StoredFile)
            .join(StoredFile, StoredFile.id == ProctoringSnapshot.file_id)
            .where(ProctoringSnapshot.interview_id == interview.id)
            .order_by(ProctoringSnapshot.captured_at)
        )
    ).all()
    frames = [
        ProctorFrameOut(
            id=snap.id,
            seconds=max(0, int((snap.captured_at - start).total_seconds())) if start else 0,
            signal=snap.signal,
            image_url=await storage.presign_get(f.bucket, f.key, public=True),
        )
        for snap, f in snap_rows
    ]

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
        proctor_frames=frames,
        review_trail=trail,
    )


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
