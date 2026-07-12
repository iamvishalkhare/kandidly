"""Internal API (SPEC §12.3) — agent/worker only, guarded by X-Service-Token
(SPEC §12.4). Never exposed through public ingress."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, service_auth
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.queue import enqueue
from app.db.models import (
    Application,
    Interview,
    QuestionPlan,
    QuestionPlanNode,
    Turn,
)
from app.domain import applications as apps
from app.domain.states import assert_interview_transition

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(service_auth)])


# --- bootstrap (SPEC §9.1) -------------------------------------------------
@router.get("/interviews/{interview_id}/bootstrap")
async def bootstrap(interview_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    plan = (
        await db.execute(select(QuestionPlan).where(QuestionPlan.interview_id == interview_id))
    ).scalar_one_or_none()
    nodes = []  # type: ignore
    if plan is not None:
        nodes = (
            (  # type: ignore
                await db.execute(
                    select(QuestionPlanNode)
                    .where(QuestionPlanNode.plan_id == plan.id)
                    .order_by(QuestionPlanNode.position)
                )
            )
            .scalars()
            .all()
        )
    req_config = {}
    app = await db.get(Application, interview.application_id)
    from app.db.models import Requisition

    req = await db.get(Requisition, interview.requisition_id)
    if req is not None:
        req_config = req.interview_config

    # Interview context bundle — read the Redis cache, rebuild from Postgres on a
    # miss (cold cache / expired TTL). This is the "fetch from Redis at room load"
    # fast path; the agent uses it for candidate-specific follow-ups.
    from app.domain.interview_context import get_cached_context, rebuild_context

    context = await get_cached_context(interview_id)
    if context is None:
        context = await rebuild_context(db, interview_id)
    context = context or {}

    return {
        "interview": {
            "id": str(interview.id),
            "status": interview.status,
            "room_name": interview.room_name,
            "elapsed_active_seconds": interview.elapsed_active_seconds,
        },
        "plan": {"id": str(plan.id), "status": plan.status} if plan else None,
        "nodes": [
            {
                "id": str(n.id),
                "position": n.position,
                "node_type": n.node_type,
                "title": n.title,
                "seed_question": n.seed_question,
                "target_criteria": n.target_criteria,
                "difficulty": n.difficulty,
                "soft_budget_seconds": n.soft_budget_seconds,
                "priority": n.priority,
                "max_followups": n.max_followups,
                "state": n.state,
            }
            for n in nodes
        ],
        "config": req_config,
        "candidate_display_name": context.get("candidate_display_name"),
        "resume_summary": context.get("resume"),
        "form_digest": context.get("form"),
        "context": context,
        "application_id": str(app.id) if app else None,
    }


# --- turns (SPEC §9.4, write-path rule 2) ----------------------------------
class TurnIn(BaseModel):
    node_id: UUID | None = None
    seq: int
    speaker: str
    text: str
    started_at: datetime
    ended_at: datetime | None = None
    stt_confidence: float | None = None
    decision: str | None = None
    meta: dict = {}


@router.post("/interviews/{interview_id}/turns")
async def create_turn(interview_id: UUID, body: TurnIn, db: AsyncSession = Depends(get_db)) -> dict:
    # Enforce monotonic seq (SPEC write-path rule 2).
    current_max = (
        await db.execute(select(func.max(Turn.seq)).where(Turn.interview_id == interview_id))
    ).scalar_one()
    if current_max is not None and body.seq <= current_max:
        raise AppError(
            "conflict",
            "Non-monotonic turn seq",
            detail={"seq": body.seq, "current_max": current_max},
        )
    turn = Turn(
        id=new_id(),
        interview_id=interview_id,
        node_id=body.node_id,
        seq=body.seq,
        speaker=body.speaker,
        text=body.text,
        started_at=body.started_at,
        ended_at=body.ended_at,
        stt_confidence=body.stt_confidence,
        decision=body.decision,
        meta=body.meta,
    )
    db.add(turn)
    await db.flush()
    # Annotate candidate turns asynchronously (SPEC §14 annotate_turn).
    if body.speaker == "candidate":
        await enqueue("annotate_turn", str(turn.id))
    return {"id": str(turn.id), "seq": turn.seq}


class TurnPatch(BaseModel):
    ended_at: datetime | None = None
    text: str | None = None
    meta: dict | None = None


@router.patch("/turns/{turn_id}")
async def patch_turn(turn_id: UUID, body: TurnPatch, db: AsyncSession = Depends(get_db)) -> dict:
    turn = await db.get(Turn, turn_id)
    if turn is None:
        raise AppError("not_found", "Turn not found")
    if body.ended_at is not None:
        turn.ended_at = body.ended_at
    if body.text is not None:
        turn.text = body.text
    if body.meta is not None:
        turn.meta = {**(turn.meta or {}), **body.meta}
    return {"ok": True}


# --- status (SPEC §8.3, §12.3) ---------------------------------------------
class StatusIn(BaseModel):
    status: str
    end_reason: str | None = None
    elapsed_active_seconds: int | None = None


@router.post("/interviews/{interview_id}/status")
async def set_status(
    interview_id: UUID, body: StatusIn, db: AsyncSession = Depends(get_db)
) -> dict:
    interview = await db.get(Interview, interview_id, with_for_update=True)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    if body.status != interview.status:
        assert_interview_transition(interview.status, body.status)
        interview.status = body.status
        if body.status == "live" and interview.started_at is None:
            interview.started_at = datetime.now(UTC)
        if body.status == "ended":
            interview.ended_at = datetime.now(UTC)
            interview.end_reason = body.end_reason
    if body.elapsed_active_seconds is not None:
        interview.elapsed_active_seconds = body.elapsed_active_seconds

    # Mirror interview terminal → application state (SPEC §8.2).
    app = await db.get(Application, interview.application_id)
    if body.status == "ended" and app and app.state == "in_interview":
        to = "completed" if body.end_reason in ("completed", "time_cap") else "abandoned"
        await apps.transition(db, app.id, to, "agent", {"end_reason": body.end_reason})
        await enqueue("finalize_interview", str(interview.id))
    return {"ok": True, "status": interview.status}


# --- heartbeat (SPEC §9.4) -------------------------------------------------
class HeartbeatIn(BaseModel):
    elapsed_active_seconds: int
    current_node_id: UUID | None = None


@router.post("/interviews/{interview_id}/heartbeat")
async def heartbeat(
    interview_id: UUID, body: HeartbeatIn, db: AsyncSession = Depends(get_db)
) -> dict:
    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    interview.elapsed_active_seconds = body.elapsed_active_seconds
    # Redis live:{id} key with TTL is written by the agent directly (SPEC §9.4);
    # this endpoint keeps the durable elapsed counter fresh.
    return {"ok": True}


class ProctorEventsIn(BaseModel):
    events: list[dict] = []


@router.post("/interviews/{interview_id}/proctor-events")
async def bulk_proctor_events(
    interview_id: UUID, body: ProctorEventsIn, db: AsyncSession = Depends(get_db)
) -> dict:
    """Agent-forwarded event batches (SPEC §10.2, §12.3). Consent is enforced
    here too (§16.1) — the agent only relays what the client sent."""
    from app.domain import proctoring

    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    await proctoring.require_consent(db, interview.application_id)
    # Forwarded batches are browser events by default (SPEC §10.2); the agent's
    # own audio/system events carry an explicit "source" per event.
    accepted = await proctoring.ingest_events(
        db,
        interview_id=interview_id,
        application_id=interview.application_id,
        events=body.events,
        default_source="browser",
    )
    return {"accepted": accepted}


class NodeCreateIn(BaseModel):
    node_type: str = "injected"
    title: str
    seed_question: str
    position: float
    provenance: dict = {}


@router.post("/interviews/{interview_id}/nodes")
async def create_node(
    interview_id: UUID, body: NodeCreateIn, db: AsyncSession = Depends(get_db)
) -> dict:
    plan = (
        await db.execute(select(QuestionPlan).where(QuestionPlan.interview_id == interview_id))
    ).scalar_one_or_none()
    if plan is None:
        raise AppError("not_found", "Plan not found")
    node = QuestionPlanNode(
        id=new_id(),
        plan_id=plan.id,
        position=int(body.position * 2),  # temp; renumber in finalize
        node_type=body.node_type,
        title=body.title,
        seed_question=body.seed_question,
        target_criteria=[],
        soft_budget_seconds=90,
        priority=3,
        provenance=body.provenance,
        state="pending",
    )
    db.add(node)
    await db.flush()
    return {"id": str(node.id)}


class NodePatch(BaseModel):
    state: str
    skip_reason: str | None = None


@router.patch("/nodes/{node_id}")
async def patch_node(node_id: UUID, body: NodePatch, db: AsyncSession = Depends(get_db)) -> dict:
    node = await db.get(QuestionPlanNode, node_id)
    if node is None:
        raise AppError("not_found", "Node not found")
    node.state = body.state
    if body.skip_reason is not None:
        node.skip_reason = body.skip_reason
    return {"ok": True}
