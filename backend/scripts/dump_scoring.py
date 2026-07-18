"""Ops diagnostic (ops.yml `dump-scoring`): print an interview's scoring state
as JSON — turns, criterion_scores with per-quote verification results, and
evaluations — so evidence-verification failures can be debugged from outside
the box. Truncated previews only; SSM caps captured output at 24 000 chars.

Run inside the backend container:
    env PYTHONPATH=/app/backend /app/.venv/bin/python \
        /app/backend/scripts/dump_scoring.py <interview-uuid>
"""

from __future__ import annotations

import asyncio
import json
import sys
from uuid import UUID


async def main(interview_id: UUID) -> None:
    from sqlalchemy import select

    from app.db.models import CriterionScore, Evaluation, Interview, Report, ScoringJob, Turn
    from app.db.session import SessionLocal
    from app.domain.scoring import verify_quote

    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None:
            print(json.dumps({"error": "interview not found"}))
            return
        turns = (
            (
                await db.execute(
                    select(Turn).where(Turn.interview_id == interview_id).order_by(Turn.seq)
                )
            )
            .scalars()
            .all()
        )
        sj = (
            await db.execute(select(ScoringJob).where(ScoringJob.interview_id == interview_id))
        ).scalar_one_or_none()
        score_rows = []
        if sj is not None:
            score_rows = (
                (
                    await db.execute(
                        select(CriterionScore).where(CriterionScore.scoring_job_id == sj.id)
                    )
                )
                .scalars()
                .all()
            )
        evaluations = (
            (await db.execute(select(Evaluation).where(Evaluation.interview_id == interview_id)))
            .scalars()
            .all()
        )
        report = (
            await db.execute(select(Report).where(Report.interview_id == interview_id))
        ).scalar_one_or_none()

    turn_text = {str(t.id): t.text for t in turns}
    out = {
        "interview": {
            "id": str(interview.id),
            "status": interview.status,
            "end_reason": interview.end_reason,
            "ended_at": str(interview.ended_at),
        },
        "turns": [
            {
                "id": str(t.id),
                "seq": t.seq,
                "speaker": t.speaker,
                "chars": len(t.text),
                "preview": t.text[:60],
            }
            for t in turns
        ],
        "scoring_job": None
        if sj is None
        else {"id": str(sj.id), "status": sj.status, "model": sj.model, "error": sj.error},
        "criterion_scores": [
            {
                "criterion": r.criterion_key,
                "run": r.run_index,
                "score": r.score,
                "confidence": r.confidence,
                "evidence": [
                    {
                        "turn_id": e.get("turn_id"),
                        "turn_known": e.get("turn_id") in turn_text,
                        "quote_ok": verify_quote(
                            e.get("quote", ""), turn_text.get(e.get("turn_id"), "")
                        ),
                        "quote_preview": (e.get("quote") or "")[:100],
                    }
                    for e in (r.evidence or [])
                ],
            }
            for r in score_rows
        ],
        "evaluations": [
            {
                "criterion": ev.criterion_key,
                "final_score": float(ev.final_score),
                "method": ev.method,
                "needs_review": ev.needs_review,
            }
            for ev in evaluations
        ],
        "report": None
        if report is None
        else {"overall_score": float(report.overall_score), "status": report.status},
    }
    print(json.dumps(out, ensure_ascii=False)[:20000])


if __name__ == "__main__":
    asyncio.run(main(UUID(sys.argv[1])))
