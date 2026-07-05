"""annotate_turn job (SPEC §14, §20.6). Best-effort per candidate turn: emit
0..3 evidence_notes. Failures logged, retried at most once."""

from __future__ import annotations

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.ids import new_id
from app.db.models import (
    EvidenceNote,
    Interview,
    Requisition,
    RubricCriterion,
    Turn,
)
from app.db.session import SessionLocal
from app.llm.clients import evidence_annotator
from app.llm.prompts import load_prompt

log = structlog.get_logger(__name__)


async def annotate_turn(ctx: dict, turn_id: str) -> None:
    async with SessionLocal() as db:
        turn = await db.get(Turn, turn_id)
        if turn is None or turn.speaker != "candidate":
            return
        interview = await db.get(Interview, turn.interview_id)
        # Resolve the rubric via the requisition.
        req = await db.get(Requisition, interview.requisition_id)  # type: ignore
        criteria = (
            (
                await db.execute(
                    select(RubricCriterion).where(RubricCriterion.rubric_id == req.rubric_id)  # type: ignore
                )
            )
            .scalars()
            .all()
        )
        criteria_digest = [{"key": c.key, "name": c.name} for c in criteria]

        # Find the preceding kandidly question for context.
        prev_q = (
            await db.execute(
                select(Turn)
                .where(
                    Turn.interview_id == interview.id,  # type: ignore
                    Turn.seq < turn.seq,
                    Turn.speaker == "kandidly",
                )
                .order_by(Turn.seq.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        question = prev_q.text if prev_q else ""
        answer = turn.text

    try:
        agent = evidence_annotator()
        prompt = (
            load_prompt("annotate", "v1")
            .replace("{criteria_digest}", str(criteria_digest))
            .replace("{question}", question)
            .replace("{answer}", answer)
        )
        result = await agent.run(prompt)
        annotations = getattr(result, "output", None) or getattr(result, "data", None) or []
    except Exception as exc:  # noqa: BLE001
        log.info("annotate_failed", turn_id=turn_id, error=str(exc))
        return

    valid_keys = {c["key"] for c in criteria_digest}
    async with SessionLocal() as db:
        for ann in annotations[:3]:
            if ann.criterion_key not in valid_keys:
                continue
            db.add(
                EvidenceNote(
                    id=new_id(),
                    interview_id=turn.interview_id,
                    turn_id=turn.id,
                    criterion_key=ann.criterion_key,
                    signal=ann.signal,
                    note=ann.note,
                    model=settings.annotate_llm,
                )
            )
        await db.commit()
