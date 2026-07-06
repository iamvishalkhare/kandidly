"""Admin/recruiter API (SPEC §12.1). Mutating routes write audit_log. Publish
gates run the normative validators (SPEC §8.1.2, §7.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db, require_role
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.ratelimit import rate_limit
from app.core.security import AuthUser
from app.db.models import (
    Application,
    CatalogEntry,
    Evaluation,
    FormSubmission,
    FormTemplate,
    Injection,
    Interview,
    InviteLink,
    Organization,
    Report,
    Requisition,
    Rubric,
    RubricCriterion,
    Turn,
    User,
)
from app.domain.audit import record_audit
from app.domain.forms import validate_field_hints, validate_template
from app.domain.links import generate_token
from app.domain.rubrics import validate_criteria
from app.schemas.api import (
    AdminApplicationDetailOut,
    AdminApplicationListOut,
    EvaluationOut,
    FormTemplateCreate,
    FormTemplateOut,
    FunnelOut,
    FunnelStageOut,
    InjectionIn,
    LinkCreate,
    LinkOut,
    ReportOut,
    ReportReviewIn,
    RequisitionCreate,
    RequisitionOut,
    RequisitionStatusIn,
    RubricCreate,
    RubricCriterionIn,
    RubricOut,
    TranscriptOut,
    TurnOut,
)
from app.schemas.interview_config import InterviewConfig

router = APIRouter(prefix="/api/admin", tags=["admin"])
_admin = Depends(require_role("admin", "recruiter"))


async def _org_id_for(db: AsyncSession, user: AuthUser):
    """Creator's org, falling back to the default org (dev tokens and rows
    predating WorkOS org sync may lack a membership)."""
    row = await db.get(User, user.user_id)
    if row is not None and row.org_id is not None:
        return row.org_id
    org_id = (
        await db.execute(
            select(Organization.id).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one_or_none()
    if org_id is None:
        raise AppError("internal_error", "No organization configured")
    return org_id


async def _upsert_catalog(
    db: AsyncSession, org_id, user: AuthUser, entries: list[tuple[str, str]]
) -> None:
    """Record builder-entered domain/skill/job-title values as autocomplete
    suggestions; duplicates are ignored."""
    values = [
        {"id": new_id(), "org_id": org_id, "kind": kind, "value": value, "created_by": user.user_id}
        for kind, value in entries
        if value and value.strip()
    ]
    if not values:
        return
    await db.execute(
        pg_insert(CatalogEntry).values(values).on_conflict_do_nothing(constraint="org_kind_value")
    )


def _template_out(t: FormTemplate) -> FormTemplateOut:
    return FormTemplateOut(
        id=t.id,
        family_id=t.family_id,
        version=t.version,
        interview_type=t.interview_type,
        title=t.title,
        schema=t.schema,
        field_hints=t.field_hints,
        status=t.status,
        created_at=t.created_at,
        published_at=t.published_at,
    )


# --- form templates (SPEC §12.1 #1–4) --------------------------------------
@router.post("/form-templates", response_model=FormTemplateOut)
async def create_form_template(
    body: FormTemplateCreate, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> FormTemplateOut:
    validate_template(body.schema)
    validate_field_hints(body.schema, body.field_hints)
    t = FormTemplate(
        id=new_id(),
        org_id=await _org_id_for(db, user),
        family_id=new_id(),
        version=1,
        interview_type=body.interview_type,
        title=body.title,
        schema=body.schema,
        field_hints=body.field_hints,
        status="draft",
        created_by=user.user_id,
    )
    db.add(t)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="form_template.create",
        entity_type="form_template",
        entity_id=t.id,
    )
    return _template_out(t)


@router.post("/form-templates/{family_id}/versions", response_model=FormTemplateOut)
async def new_template_version(
    family_id: UUID,
    body: FormTemplateCreate,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> FormTemplateOut:
    validate_template(body.schema)
    validate_field_hints(body.schema, body.field_hints)
    latest = (
        await db.execute(
            select(func.max(FormTemplate.version)).where(FormTemplate.family_id == family_id)
        )
    ).scalar_one()
    if latest is None:
        raise AppError("not_found", "Template family not found")
    t = FormTemplate(
        id=new_id(),
        org_id=await _org_id_for(db, user),
        family_id=family_id,
        version=latest + 1,
        interview_type=body.interview_type,
        title=body.title,
        schema=body.schema,
        field_hints=body.field_hints,
        status="draft",
        created_by=user.user_id,
    )
    db.add(t)
    return _template_out(t)


@router.post("/form-templates/{template_id}/publish", response_model=FormTemplateOut)
async def publish_template(
    template_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> FormTemplateOut:
    t = await db.get(FormTemplate, template_id)
    if t is None:
        raise AppError("not_found", "Template not found")
    validate_template(t.schema)  # re-validate on publish (SPEC §8.1.2)
    validate_field_hints(t.schema, t.field_hints)
    t.status = "published"
    t.published_at = datetime.now(UTC)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="form_template.publish",
        entity_type="form_template",
        entity_id=t.id,
    )
    return _template_out(t)


@router.get("/form-templates", response_model=list[FormTemplateOut])
async def list_templates(
    interview_type: str | None = None,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> list[FormTemplateOut]:
    stmt = select(FormTemplate).order_by(FormTemplate.family_id, FormTemplate.version.desc())
    if interview_type:
        stmt = stmt.where(FormTemplate.interview_type == interview_type)
    rows = (await db.execute(stmt)).scalars().all()
    return [_template_out(t) for t in rows]


# --- rubrics (SPEC §12.1 #5, §7.3) -----------------------------------------
async def _rubric_out(db: AsyncSession, r: Rubric) -> RubricOut:
    crits = (
        (
            await db.execute(
                select(RubricCriterion)
                .where(RubricCriterion.rubric_id == r.id)
                .order_by(RubricCriterion.display_order)
            )
        )
        .scalars()
        .all()
    )
    return RubricOut(
        id=r.id,
        family_id=r.family_id,
        version=r.version,
        interview_type=r.interview_type,
        title=r.title,
        status=r.status,
        criteria=[
            RubricCriterionIn(
                key=c.key,
                name=c.name,
                description=c.description,
                weight=float(c.weight),
                display_order=c.display_order,
                level_anchors=c.level_anchors,
            )
            for c in crits
        ],
    )


@router.post("/rubrics", response_model=RubricOut)
async def create_rubric(
    body: RubricCreate, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> RubricOut:
    r = Rubric(
        id=new_id(),
        org_id=await _org_id_for(db, user),
        family_id=new_id(),
        version=1,
        interview_type=body.interview_type,
        title=body.title,
        status="draft",
        created_by=user.user_id,
    )
    db.add(r)
    await db.flush()
    for c in body.criteria:
        db.add(
            RubricCriterion(
                id=new_id(),
                rubric_id=r.id,
                key=c.key,
                name=c.name,
                description=c.description,
                weight=c.weight,
                display_order=c.display_order,
                level_anchors=[a.model_dump() for a in c.level_anchors],
            )
        )
    return await _rubric_out(db, r)


@router.post("/rubrics/{rubric_id}/publish", response_model=RubricOut)
async def publish_rubric(
    rubric_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> RubricOut:
    r = await db.get(Rubric, rubric_id)
    if r is None:
        raise AppError("not_found", "Rubric not found")
    crits = (
        (await db.execute(select(RubricCriterion).where(RubricCriterion.rubric_id == r.id)))
        .scalars()
        .all()
    )
    validate_criteria(
        [{"key": c.key, "weight": float(c.weight), "level_anchors": c.level_anchors} for c in crits]
    )
    r.status = "published"
    r.published_at = datetime.now(UTC)
    await record_audit(
        db, actor_id=user.user_id, action="rubric.publish", entity_type="rubric", entity_id=r.id
    )
    return await _rubric_out(db, r)


@router.get("/rubrics", response_model=list[RubricOut])
async def list_rubrics(
    interview_type: str | None = None,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> list[RubricOut]:
    stmt = select(Rubric).order_by(Rubric.family_id, Rubric.version.desc())
    if interview_type:
        stmt = stmt.where(Rubric.interview_type == interview_type)
    rows = (await db.execute(stmt)).scalars().all()
    return [await _rubric_out(db, r) for r in rows]


# --- requisitions (SPEC §12.1 #6–9) ----------------------------------------
def _req_out(r: Requisition) -> RequisitionOut:
    return RequisitionOut(
        id=r.id,
        code=r.code,
        title=r.title,
        interview_type=r.interview_type,
        domain=r.domain,
        technical_requirements=list(r.technical_requirements or []),
        role_objective=r.role_objective,
        sample_questions=list(r.sample_questions or []),
        form_template_id=r.form_template_id,
        rubric_id=r.rubric_id,
        status=r.status,
        interview_config=r.interview_config,
        opens_at=r.opens_at,
        closes_at=r.closes_at,
    )


@router.post("/requisitions", response_model=RequisitionOut)
async def create_requisition(
    body: RequisitionCreate, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> RequisitionOut:
    cfg = (body.interview_config or InterviewConfig()).model_dump()
    org_id = await _org_id_for(db, user)
    seq = (await db.execute(sa_text("SELECT nextval('requisition_code_seq')"))).scalar_one()
    r = Requisition(
        id=new_id(),
        org_id=org_id,
        code=f"REQ-{seq:04d}",
        title=body.title,
        interview_type=body.interview_type,
        domain=body.domain,
        technical_requirements=list(body.technical_requirements),
        role_objective=body.role_objective,
        sample_questions=[q.model_dump() for q in body.sample_questions],
        form_template_id=body.form_template_id,
        rubric_id=body.rubric_id,
        status="draft",
        interview_config=cfg,
        created_by=user.user_id,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
    )
    db.add(r)
    await _upsert_catalog(
        db,
        org_id,
        user,
        [("domain", body.domain or ""), ("job_title", body.title)]
        + [("skill", s) for s in body.technical_requirements],
    )
    await record_audit(
        db,
        actor_id=user.user_id,
        action="requisition.create",
        entity_type="requisition",
        entity_id=r.id,
    )
    return _req_out(r)


@router.get("/requisitions", response_model=list[RequisitionOut])
async def list_requisitions(user: AuthUser = _admin, db: AsyncSession = Depends(get_db)):
    query = select(Requisition).order_by(Requisition.created_at.desc())
    res = await db.execute(query)
    reqs = res.scalars().all()
    # we need to populate application_count for each (if we want, or leave 0 for now)
    # The Pydantic schema doesn't have application_count by default but Dashboard uses it.
    # We can just return reqs.
    return reqs


@router.get("/requisitions/{req_id}", response_model=RequisitionOut)
async def get_requisition(
    req_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
):
    req = await db.get(Requisition, req_id)
    if not req:
        raise AppError("not_found", "Requisition not found")
    return req


@router.post("/requisitions/{req_id}/status", response_model=RequisitionOut)
async def set_requisition_status(
    req_id: UUID,
    body: RequisitionStatusIn,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> RequisitionOut:
    r = await db.get(Requisition, req_id)
    if r is None:
        raise AppError("not_found", "Requisition not found")
    target = body.status
    allowed = {
        "draft": {"open"},
        "open": {"paused", "closed"},
        "paused": {"open", "closed"},
        "closed": set(),
    }
    if target not in allowed.get(r.status, set()):
        raise AppError("invalid_transition", f"Cannot move requisition {r.status} → {target}")
    if target == "open":
        # Invariant (SPEC §7.4): template & rubric MUST be published.
        tmpl = await db.get(FormTemplate, r.form_template_id)
        rub = await db.get(Rubric, r.rubric_id)
        if tmpl.status != "published" or rub.status != "published":  # type: ignore
            raise AppError("conflict", "Template and rubric must be published before opening")
    r.status = target
    r.updated_at = datetime.now(UTC)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="requisition.status",
        entity_type="requisition",
        entity_id=r.id,
        meta={"status": target},
    )
    return _req_out(r)


@router.post("/requisitions/{req_id}/links", response_model=LinkOut)
async def create_link(
    req_id: UUID, body: LinkCreate, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> LinkOut:
    r = await db.get(Requisition, req_id)
    if r is None:
        raise AppError("not_found", "Requisition not found")
    if body.kind not in ("open", "personal"):
        raise AppError("validation_error", "kind must be 'open' or 'personal'")
    if body.kind == "personal" and not body.email:
        raise AppError("validation_error", "personal links require an email")
    link = InviteLink(
        id=new_id(),
        requisition_id=r.id,
        token=generate_token(),
        kind=body.kind,
        email=body.email,
        max_uses=body.max_uses,
        expires_at=body.expires_at,
        created_by=user.user_id,
    )
    db.add(link)
    url = f"{settings.base_url_web}/i/{link.token}"
    await record_audit(
        db,
        actor_id=user.user_id,
        action="link.create",
        entity_type="invite_link",
        entity_id=link.id,
    )
    return LinkOut(id=link.id, token=link.token, kind=link.kind, url=url)


@router.post("/links/{link_id}/revoke", response_model=LinkOut)
async def revoke_link(
    link_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> LinkOut:
    link = await db.get(InviteLink, link_id)
    if link is None:
        raise AppError("not_found", "Link not found")
    link.revoked_at = datetime.now(UTC)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="link.revoke",
        entity_type="invite_link",
        entity_id=link.id,
    )
    return LinkOut(
        id=link.id, token=link.token, kind=link.kind, url=f"{settings.base_url_web}/i/{link.token}"
    )


# --- observer + inject (SPEC §12.1 #16–17, §9.7) ---------------------------
@router.post("/interviews/{interview_id}/observer-token")
async def observer_token(
    interview_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> dict:
    from app.domain.interviews import mint_observer_token

    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    if interview.status not in ("live", "paused", "wrap_up"):
        raise AppError("conflict", "Interview is not observable")
    req = await db.get(Requisition, interview.requisition_id)
    if not req.interview_config.get("observer_allowed", True):  # type: ignore
        raise AppError("forbidden", "Observation disabled for this requisition")
    return {
        "livekit_url": settings.livekit_url,
        "token": mint_observer_token(interview.room_name, user.user_id),  # type: ignore
    }


@router.post("/interviews/{interview_id}/inject", dependencies=[rate_limit("inject", 6)])
async def inject(
    interview_id: UUID,
    body: InjectionIn,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.core.queue import get_pool

    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    injection = Injection(
        id=new_id(),
        interview_id=interview_id,
        requested_by=user.user_id,
        question_text=body.question_text,
        status="queued",
    )
    db.add(injection)
    await db.flush()
    # Notify the agent via Redis pub/sub (SPEC §9.7).
    pool = await get_pool()
    await pool.publish(f"inject:{interview_id}", str(injection.id))
    return {"injection_id": str(injection.id), "status": "queued"}


# --- Phase-1 text-chat harness (SPEC §18.5) ---------------------------------
class ChatReplyIn(BaseModel):
    text: str


@router.post("/interviews/{interview_id}/chat/start")
async def chat_start(
    interview_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> dict:
    from app.domain import harness

    result = await harness.start(db, interview_id)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="interview.chat_start",
        entity_type="interview",
        entity_id=interview_id,
    )
    return result


@router.post("/interviews/{interview_id}/chat/reply")
async def chat_reply(
    interview_id: UUID,
    body: ChatReplyIn,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.core.queue import enqueue
    from app.db.models import Application
    from app.domain import harness
    from app.domain.applications import transition

    result = await harness.reply(db, interview_id, body.text)
    if result.get("ended"):
        # Mirror interview end into the application when it was in_interview,
        # then finalize (closes nodes, enqueues scoring) — SPEC §8.2, §11.1.
        interview = await db.get(Interview, interview_id)
        app = await db.get(Application, interview.application_id)  # type: ignore
        if app and app.state == "in_interview":
            await transition(db, app.id, "completed", "agent", {"end_reason": "completed"})
        await enqueue("finalize_interview", str(interview_id))
    return result


# --- missing endpoints (SPEC §12.1 #11-15, 18) ------------------------------
@router.get("/requisitions/{req_id}/applications", response_model=list[AdminApplicationListOut])
async def list_applications(
    req_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> list[AdminApplicationListOut]:
    # The external users table has no display name (SPEC §3.6: id/email/role only);
    # derive it from the KYI form's full_name answer, falling back to the email.
    stmt = (
        select(Application, User.email, FormSubmission.answers, Report.overall_score)
        .join(User, Application.candidate_id == User.id)
        .outerjoin(FormSubmission, Application.form_submission_id == FormSubmission.id)
        .outerjoin(Interview, Application.interview_id == Interview.id)
        .outerjoin(Report, Interview.id == Report.interview_id)
        .where(Application.requisition_id == req_id)
        .order_by(Application.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        AdminApplicationListOut(
            id=app.id,
            candidate_name=(answers or {}).get("full_name") or email.split("@")[0],
            candidate_email=email,
            state=app.state,
            created_at=app.created_at,
            overall_score=float(score) if score is not None else None,
        )
        for app, email, answers, score in rows
    ]


@router.get("/applications/{app_id}", response_model=AdminApplicationDetailOut)
async def get_application_detail(
    app_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> AdminApplicationDetailOut:
    app = await db.get(Application, app_id)
    if app is None:
        raise AppError("not_found", "Application not found")
    candidate = await db.get(User, app.candidate_id)
    form = await db.get(FormSubmission, app.form_submission_id) if app.form_submission_id else None
    interview = await db.get(Interview, app.interview_id) if app.interview_id else None
    report = None
    if interview:
        report = (
            await db.execute(select(Report).where(Report.interview_id == interview.id))
        ).scalar_one_or_none()

    answers = form.answers if form else {}
    fallback_name = candidate.email.split("@")[0] if candidate else "Unknown"
    return AdminApplicationDetailOut(
        id=app.id,
        requisition_id=app.requisition_id,
        candidate_id=app.candidate_id,
        candidate_name=(answers or {}).get("full_name") or fallback_name,
        candidate_email=candidate.email if candidate else "Unknown",
        state=app.state,
        state_timestamps=app.state_timestamps,
        form_answers=form.answers if form else None,
        interview_id=interview.id if interview else None,
        interview_status=interview.status if interview else None,
        overall_score=report.overall_score if report else None,
    )


@router.get("/interviews/{interview_id}/transcript", response_model=TranscriptOut)
async def get_transcript(
    interview_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> TranscriptOut:
    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    turns = (
        (await db.execute(select(Turn).where(Turn.interview_id == interview_id).order_by(Turn.seq)))
        .scalars()
        .all()
    )
    return TranscriptOut(
        interview_id=interview_id,
        turns=[
            TurnOut(
                id=t.id,
                seq=t.seq,
                speaker=t.speaker,
                text=t.text,
                started_at=t.started_at,
                ended_at=t.ended_at,
            )
            for t in turns
        ],
    )


@router.get("/interviews/{interview_id}/report", response_model=ReportOut)
async def get_report(
    interview_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> ReportOut:
    report = (
        await db.execute(select(Report).where(Report.interview_id == interview_id))
    ).scalar_one_or_none()
    if report is None:
        raise AppError("not_found", "Report not found")
    evaluations = (
        (await db.execute(select(Evaluation).where(Evaluation.interview_id == interview_id)))
        .scalars()
        .all()
    )
    return ReportOut(
        id=report.id,
        interview_id=report.interview_id,
        overall_score=float(report.overall_score),
        summary=report.summary,
        strengths=report.strengths,
        concerns=report.concerns,
        coverage=report.coverage,
        status=report.status,
        review_decision=report.review_decision,
        review_notes=report.review_notes,
        evaluations=[
            EvaluationOut(
                criterion_key=e.criterion_key,
                final_score=float(e.final_score),
                evidence=e.evidence,
                rationale=e.rationale,
            )
            for e in evaluations
        ],
    )


@router.post("/interviews/{interview_id}/report/review")
async def review_report(
    interview_id: UUID,
    body: ReportReviewIn,
    user: AuthUser = _admin,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.domain.applications import transition

    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    report = (
        await db.execute(select(Report).where(Report.interview_id == interview_id))
    ).scalar_one_or_none()
    if report is None:
        raise AppError("not_found", "Report not found")

    report.review_decision = body.decision
    report.review_notes = body.notes
    report.reviewed_by = user.user_id
    report.reviewed_at = datetime.now(UTC)
    report.status = "final"  # SPEC §12.1 #14

    await transition(
        db,
        interview.application_id,
        "reviewed",
        "admin",
        {"decision": body.decision, "reviewer": str(user.user_id)},
    )
    await record_audit(
        db,
        actor_id=user.user_id,
        action="report.review",
        entity_type="report",
        entity_id=report.id,
        meta={"decision": body.decision},
    )
    return {"status": "ok"}


@router.get("/funnel", response_model=FunnelOut)
async def get_funnel(user: AuthUser = _admin, db: AsyncSession = Depends(get_db)) -> FunnelOut:
    rows = (
        await db.execute(select(Application.state, func.count()).group_by(Application.state))
    ).all()
    return FunnelOut(stages=[FunnelStageOut(state=state, count=count) for state, count in rows])


@router.get("/requisitions/{req_id}/funnel")
async def get_requisition_funnel(
    req_id: UUID, user: AuthUser = _admin, db: AsyncSession = Depends(get_db)
) -> dict:
    """Per-requisition funnel (SPEC §12.1 #18), powered by the v_funnel view
    (§15.4): counts by state + median seconds spent in each state."""
    from sqlalchemy import text as sa_text

    rows = (
        await db.execute(
            sa_text(
                "SELECT state, count, median_seconds_in_state FROM v_funnel "
                "WHERE requisition_id = :rid"
            ),
            {"rid": str(req_id)},
        )
    ).all()
    return {
        "stages": [
            {
                "state": state,
                "count": count,
                "median_seconds_in_state": float(med) if med is not None else None,
            }
            for state, count, med in rows
        ]
    }
